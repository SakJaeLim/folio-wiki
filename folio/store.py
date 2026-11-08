import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .anchors import comparison, definitions, links, units
from .documents import digest, public_files, sections


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "wiki.sqlite3"
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS workspace(id INTEGER PRIMARY KEY CHECK(id=1), folder TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources(path TEXT, version TEXT, body TEXT NOT NULL,
                    PRIMARY KEY(path,version));
                CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, files TEXT NOT NULL,
                    created TEXT NOT NULL, kb TEXT, remote_doc TEXT, pages TEXT NOT NULL DEFAULT '[]',
                    engine TEXT NOT NULL DEFAULT 'pending', detail TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS current(id INTEGER PRIMARY KEY CHECK(id=1), snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS topics(name TEXT PRIMARY KEY, generation INTEGER NOT NULL,
                    candidates TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, topic TEXT NOT NULL,
                    generation INTEGER NOT NULL, selection TEXT NOT NULL, actor TEXT NOT NULL,
                    note TEXT NOT NULL, evidence TEXT NOT NULL, created TEXT NOT NULL,
                    UNIQUE(topic,generation));
            """)
            db.execute("BEGIN IMMEDIATE")
            if "comparison" not in {
                r["name"] for r in db.execute("PRAGMA table_info(topics)")
            }:
                db.execute("ALTER TABLE topics ADD COLUMN comparison TEXT")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def sync(self, folder):
        docs = public_files(folder)
        refs = {p: d["version"] for p, d in sorted(docs.items())}
        manifest = digest(pack(refs))
        groups = {}
        for doc in docs.values():
            refs_by_label = definitions(doc["body"])
            for item in sections(doc):
                item["references"] = links(item["quote"], refs_by_label)
                groups.setdefault(item["topic"], []).append(item)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            root_key = str(Path(folder).resolve(strict=True))
            workspace = db.execute("SELECT folder FROM workspace WHERE id=1").fetchone()
            if workspace and Path(workspace["folder"]) != Path(root_key):
                raise ValueError("이 저장 공간은 다른 폴더에 연결되어 있습니다.")
            db.execute("INSERT OR IGNORE INTO workspace VALUES (1,?)", (root_key,))
            prev = db.execute("SELECT snapshot FROM current WHERE id=1").fetchone()
            migrated = db.execute("PRAGMA user_version").fetchone()[0] >= 1
            if prev and prev[0] == manifest and migrated:
                return manifest
            for d in docs.values():
                db.execute(
                    "INSERT OR IGNORE INTO sources VALUES (?,?,?)",
                    (d["path"], d["version"], d["body"]),
                )
            db.execute(
                "INSERT OR IGNORE INTO snapshots(id,files,created) VALUES (?,?,?)",
                (manifest, pack(refs), now()),
            )
            existing = {r["name"]: r for r in db.execute("SELECT * FROM topics")}
            for topic in sorted(set(existing) | set(groups)):
                items = sorted(
                    groups.get(topic, []), key=lambda x: (x["path"], x["start"])
                )
                candidates = pack(items)
                prior = existing.get(topic)
                if migrated and prior and prior["candidates"] == candidates:
                    continue
                if not prior and (
                    len({i["path"] for i in items}) < 2
                    or len({" ".join(i["quote"].split()) for i in items}) < 2
                ):
                    continue
                decision = db.execute(
                    "SELECT selection,evidence FROM decisions WHERE topic=? ORDER BY id DESC LIMIT 1",
                    (topic,),
                ).fetchone()
                status, change = "open", None
                if decision:
                    selection = decision["selection"]
                    if selection in ("hold", "withdraw"):
                        status = "held" if selection == "hold" else "adopted"
                    else:
                        chosen = next(
                            c
                            for c in json.loads(decision["evidence"])
                            if c["id"] == selection
                        )
                        if "references" not in chosen:
                            archived = db.execute(
                                "SELECT body FROM sources WHERE path=? AND version=?",
                                (chosen["path"], chosen["version"]),
                            ).fetchone()
                            chosen["references"] = links(
                                chosen["quote"], definitions(archived["body"])
                            )
                        change = comparison(chosen, items)
                        status = "review_again" if change else "adopted"
                generation = prior["generation"] + 1 if prior else 1
                db.execute(
                    "INSERT OR REPLACE INTO topics(name,generation,candidates,status,comparison) VALUES (?,?,?,?,?)",
                    (
                        topic,
                        generation,
                        candidates,
                        status,
                        pack(change) if change else None,
                    ),
                )
            db.execute("INSERT OR REPLACE INTO current VALUES (1,?)", (manifest,))
            db.execute("PRAGMA user_version=1")
        return manifest

    def decide(self, topic, generation, selection, actor, note, unit=None):
        if not all(
            isinstance(v, str) and v.strip() for v in (topic, selection, actor, note)
        ):
            raise ValueError("담당자 이름과 채택 이유를 입력해 주세요.")
        if len(actor) > 80 or len(note) > 2000:
            raise ValueError(
                "담당자 이름은 80자, 이유는 2,000자까지 입력할 수 있습니다."
            )
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM topics WHERE name=?", (topic,)).fetchone()
            if not row or row["generation"] != generation or row["status"] == "adopted":
                raise Conflict(
                    "자료나 결정이 바뀌었습니다. 현재 원문을 다시 확인해 주세요."
                )
            items = json.loads(row["candidates"])
            if selection not in {"withdraw", "hold"} and not any(
                i["id"] == selection for i in items
            ):
                raise Conflict("현재 원문 중에서 선택해 주세요.")
            if unit is not None:
                chosen = next((c for c in items if c["id"] == selection), None)
                if (
                    chosen is None
                    or type(unit) is not int
                    or not 0 <= unit < len(units(chosen))
                ):
                    raise ValueError("현재 원문에 있는 문장을 선택해 주세요.")
                chosen["unit"] = unit
            db.execute(
                "INSERT INTO decisions(topic,generation,selection,actor,note,evidence,created) VALUES(?,?,?,?,?,?,?)",
                (
                    topic,
                    generation,
                    selection,
                    actor.strip(),
                    note.strip(),
                    pack(items),
                    now(),
                ),
            )
            if selection == "hold":
                db.execute(
                    "UPDATE topics SET status='held',comparison=NULL,generation=generation+1 WHERE name=?",
                    (topic,),
                )
            else:
                db.execute(
                    "UPDATE topics SET status='adopted',comparison=NULL WHERE name=?",
                    (topic,),
                )

    def snapshot(self):
        with self.db() as db:
            row = db.execute(
                "SELECT s.* FROM current c JOIN snapshots s ON c.snapshot=s.id"
            ).fetchone()
            return dict(row) if row else None

    def engine_update(self, snapshot, **values):
        permitted = {"engine", "detail", "pages", "kb", "remote_doc"}
        if not values or not set(values) <= permitted:
            raise ValueError("Unknown engine field")
        with self.db() as db:
            db.execute(
                "UPDATE snapshots SET "
                + ",".join(f"{col}=?" for col in values)
                + " WHERE id=?",
                (*values.values(), snapshot),
            )

    def source(self, path, version):
        with self.db() as db:
            row = db.execute(
                "SELECT * FROM sources WHERE path=? AND version=?", (path, version)
            ).fetchone()
        if not row:
            raise KeyError("이 원문 버전을 찾을 수 없습니다.")
        return dict(row)

    def view(self):
        with self.db() as db:
            db.execute("BEGIN")
            snapshot = db.execute(
                "SELECT s.* FROM current c JOIN snapshots s ON c.snapshot=s.id"
            ).fetchone()
            topics = [dict(x) for x in db.execute("SELECT * FROM topics ORDER BY name")]
            decisions = [
                dict(x) for x in db.execute("SELECT * FROM decisions ORDER BY id DESC")
            ]
        for t in topics:
            t["candidates"] = json.loads(t["candidates"])
            t["comparison"] = json.loads(t["comparison"]) if t["comparison"] else None
            for c in t["candidates"]:
                c["units"] = units(c)
        for d in decisions:
            d["evidence"] = json.loads(d["evidence"])
            chosen = next((c for c in d["evidence"] if c["id"] == d["selection"]), None)
            if chosen and "unit" in chosen:
                d["excerpt"] = units(chosen)[chosen["unit"]]
        s = dict(snapshot) if snapshot else {}
        return {
            "snapshot": s.get("id"),
            "files": json.loads(s.get("files", "{}")),
            "engine": s.get("engine", "pending"),
            "detail": s.get("detail", ""),
            "pages": json.loads(s.get("pages", "[]")),
            "topics": topics,
            "decisions": decisions,
        }
