import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import companions
from .anchors import comparison, definitions, links, units
from .cross_sections import with_cross_changes
from .documents import digest, public_files, sections


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def source_sections(doc):
    refs = definitions(doc["body"])
    items = sections(doc)
    for item in items:
        item["references"] = links(item["quote"], refs)
    return items


def edition_reader(db, editions):
    def edition(path, version, *, companion=False):
        if (path, version) not in editions:
            saved = db.execute(
                "SELECT * FROM sources WHERE path=? AND version=?", (path, version)
            ).fetchone()
            editions[path, version] = source_sections(dict(saved))
        items = editions[path, version]
        if companion and not items:
            body = db.execute(
                "SELECT body FROM sources WHERE path=? AND version=?", (path, version)
            ).fetchone()["body"]
            lines = body.splitlines()
            if lines:
                return [
                    {
                        "topic": "문서 본문",
                        "path": path,
                        "version": version,
                        "start": 1,
                        "end": len(lines),
                        "quote": "\n".join(lines),
                        "references": definitions(body),
                    }
                ]
        return items

    return edition


def changed_evidence(db, chosen, items, editions, current_version, bundle):
    path, version = chosen["path"], chosen["version"]
    key = path, version
    edition = edition_reader(db, editions)

    if "references" not in chosen:
        # Legacy decisions stored a section ID and a byte-exact source version.
        archived = next(item for item in edition(*key) if item["id"] == chosen["id"])
        chosen["references"] = archived["references"]
    change = comparison(chosen, items)
    if not current_version or (change and change["reason"] != "exception"):
        return change
    if current_version != version:
        change = with_cross_changes(
            chosen, edition(*key), editions[path, current_version], change
        )
    if chosen.get("publication_bundle"):
        return companions.compare(
            chosen,
            edition(*key),
            editions[path, current_version],
            bundle,
            change,
            edition,
        )
    return change


def bind_previous_decision(db, decision_id, chosen, current_version, bundle):
    if "publication_bundle" in chosen:
        return
    saved = db.execute(
        "SELECT baseline FROM decision_origins WHERE decision=?", (decision_id,)
    ).fetchone()
    if saved:
        chosen["publication_bundle"] = json.loads(saved["baseline"])
    elif bundle and current_version == chosen["version"]:
        # Only register the original adopted bytes. Keep the initial identity
        # and empty attachment baseline even after restart or path reuse.
        baseline = {**bundle, "members": {}}
        db.execute(
            "INSERT INTO decision_origins VALUES (?,?)", (decision_id, pack(baseline))
        )
        chosen["publication_bundle"] = baseline


class Conflict(ValueError):
    pass


def prepare_evidence(db, row, selection, unit, scope, audience):
    if (
        not isinstance(scope, str)
        or not isinstance(audience, str)
        or len(audience) > 160
    ):
        raise ValueError("적용할 사업 절과 대상 이름을 확인해 주세요.")
    scope, audience = scope.strip(), audience.strip()
    items = json.loads(row["candidates"])
    chosen = next((c for c in items if c["id"] == selection), None)
    if chosen is None:
        if selection not in ("withdraw", "hold"):
            raise Conflict("현재 원문 중에서 선택해 주세요.")
        if unit is not None or scope or audience:
            raise ValueError("원문을 선택해야 적용 범위를 지정할 수 있습니다.")
        return items, []
    if unit is not None:
        if type(unit) is not int or not 0 <= unit < len(units(chosen)):
            raise ValueError("현재 원문에 있는 문장을 선택해 주세요.")
        chosen["unit"] = unit
    snapshot = db.execute(
        "SELECT headings,bundles FROM snapshots JOIN current ON snapshots.id=current.snapshot"
    ).fetchone()
    if scope and scope not in json.loads(snapshot["headings"]).get(chosen["path"], []):
        raise Conflict("현재 원문의 사업 절을 선택해 주세요.")
    if scope or audience:
        chosen.update(scope=scope, audience=audience)
    bundle = json.loads(snapshot["bundles"]).get(chosen["path"])
    matches = []
    if bundle:
        chosen["publication_bundle"] = bundle
        read = edition_reader(db, {})
        matches = list(
            companions.evidence(
                chosen, read(chosen["path"], chosen["version"]), bundle, read
            ).values()
        )
        chosen["companion_evidence"] = matches
    return items, matches


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
            if "headings" not in {
                r["name"] for r in db.execute("PRAGMA table_info(snapshots)")
            }:
                db.execute(
                    "ALTER TABLE snapshots ADD COLUMN headings TEXT NOT NULL DEFAULT '{}'"
                )
            if "bundles" not in {
                r["name"] for r in db.execute("PRAGMA table_info(snapshots)")
            }:
                db.execute(
                    "ALTER TABLE snapshots ADD COLUMN bundles TEXT NOT NULL DEFAULT '{}'"
                )
            db.execute(
                "CREATE TABLE IF NOT EXISTS decision_origins(decision INTEGER PRIMARY KEY, baseline TEXT NOT NULL)"
            )

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def sync(self, folder, *, workspace=None, notice_receipt=None):
        docs = public_files(folder)
        refs = {p: d["version"] for p, d in sorted(docs.items())}
        catalog = companions.read_catalog(folder, docs)
        bundles = companions.bundles(catalog, refs)
        manifest = (
            digest(pack({"files": refs, "catalog": catalog}))
            if catalog
            else digest(pack(refs))
        )
        groups = {}
        editions = {}
        for doc in docs.values():
            items = source_sections(doc)
            editions[doc["path"], doc["version"]] = items
            for item in items:
                groups.setdefault(item["topic"], []).append(item)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            root_key = str(Path(workspace or folder).resolve(strict=True))
            if notice_receipt is not None:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS notice_import(id INTEGER PRIMARY KEY CHECK(id=1), receipt TEXT NOT NULL)"
                )
                db.execute(
                    "INSERT OR REPLACE INTO notice_import VALUES(1,?)",
                    (pack(notice_receipt),),
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS notice_original(sha TEXT PRIMARY KEY, name TEXT NOT NULL)"
                )
                db.executemany(
                    "INSERT OR IGNORE INTO notice_original VALUES(?,?)",
                    [
                        (f["raw_sha256"], f["name"])
                        for f in notice_receipt["files"]
                        if "raw_sha256" in f
                    ],
                )
            workspace = db.execute("SELECT folder FROM workspace WHERE id=1").fetchone()
            if workspace and Path(workspace["folder"]) != Path(root_key):
                raise ValueError("이 저장 공간은 다른 폴더에 연결되어 있습니다.")
            db.execute("INSERT OR IGNORE INTO workspace VALUES (1,?)", (root_key,))
            prev = db.execute(
                "SELECT s.id,s.bundles FROM current c JOIN snapshots s ON s.id=c.snapshot WHERE c.id=1"
            ).fetchone()
            migrated = db.execute("PRAGMA user_version").fetchone()[0] >= 4
            if prev and prev["id"] == manifest and migrated:
                return manifest
            previous_bundles = json.loads(prev["bundles"]) if prev else {}
            changed_roots = {
                p
                for p in previous_bundles.keys() | bundles.keys()
                if previous_bundles.get(p) != bundles.get(p)
            }
            for d in docs.values():
                db.execute(
                    "INSERT OR IGNORE INTO sources VALUES (?,?,?)",
                    (d["path"], d["version"], d["body"]),
                )
            db.execute(
                "INSERT OR IGNORE INTO snapshots(id,files,created) VALUES (?,?,?)",
                (manifest, pack(refs), now()),
            )
            headings = {
                p: list(dict.fromkeys(i["topic"] for i in editions[p, v]))
                for p, v in refs.items()
            }
            db.execute(
                "UPDATE snapshots SET headings=?,bundles=? WHERE id=?",
                (pack(headings), pack(bundles), manifest),
            )
            existing = {r["name"]: r for r in db.execute("SELECT * FROM topics")}
            for topic in sorted(set(existing) | set(groups)):
                items = sorted(
                    groups.get(topic, []), key=lambda x: (x["path"], x["start"])
                )
                candidates = pack(items)
                prior = existing.get(topic)
                if (
                    migrated
                    and prior
                    and prior["candidates"] == candidates
                    and not any(i["path"] in changed_roots for i in items)
                ):
                    continue
                linked = any(
                    any(
                        topic in bundles.get(i["path"], {}).get(field, {})
                        for field in ("rule_terms", "proof_targets")
                    )
                    for i in items
                )
                if (
                    not prior
                    and not linked
                    and (
                        notice_receipt is not None
                        or len({i["path"] for i in items}) < 2
                        or len({" ".join(i["quote"].split()) for i in items}) < 2
                    )
                ):
                    continue
                decision = db.execute(
                    "SELECT id,selection,evidence FROM decisions WHERE topic=? ORDER BY id DESC LIMIT 1",
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
                        path = chosen["path"]
                        bundle = bundles.get(path)
                        bind_previous_decision(
                            db, decision["id"], chosen, refs.get(path), bundle
                        )
                        change = changed_evidence(
                            db, chosen, items, editions, refs.get(path), bundle
                        )
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
            if not migrated:
                db.execute("PRAGMA user_version=4")
        return manifest

    def preview(self, topic, generation, selection, unit=None, scope="", audience=""):
        with self.db() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM topics WHERE name=?", (topic,)).fetchone()
            if not row or row["generation"] != generation:
                raise Conflict("원문이 바뀌었습니다. 다시 확인해 주세요.")
            return prepare_evidence(db, row, selection, unit, scope, audience)[1]

    def decide(
        self,
        topic,
        generation,
        selection,
        actor,
        note,
        unit=None,
        scope="",
        audience="",
        *,
        notice_revision=None,
    ):
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
            if notice_revision is not None:
                active = db.execute(
                    "SELECT receipt FROM notice_import WHERE id=1"
                ).fetchone()
                if (
                    not active
                    or json.loads(active["receipt"])["revision"] != notice_revision
                ):
                    raise Conflict("공고 판본이 바뀌었습니다. 다시 확인해 주세요.")
            row = db.execute("SELECT * FROM topics WHERE name=?", (topic,)).fetchone()
            if not row or row["generation"] != generation or row["status"] == "adopted":
                raise Conflict(
                    "자료나 결정이 바뀌었습니다. 현재 원문을 다시 확인해 주세요."
                )
            items, _ = prepare_evidence(db, row, selection, unit, scope, audience)
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
            "headings": json.loads(s.get("headings", "{}")),
            "publications": json.loads(s.get("bundles", "{}")),
            "engine": s.get("engine", "pending"),
            "detail": s.get("detail", ""),
            "pages": json.loads(s.get("pages", "[]")),
            "topics": topics,
            "decisions": decisions,
        }
