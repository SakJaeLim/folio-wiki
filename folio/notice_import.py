"""Import a public notice into its own Folio decision store."""

import hashlib
import json
import os
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import bizinfo
from .documents import digest
from .notice_text import attachment_md, candidate_terms, pages, root_rules
from .store import Conflict, Store, pack


class NoticeImports:
    def __init__(self, path, read=bizinfo.fetch):
        self.path = Path(path)
        self.read = read
        self.lock = threading.RLock()

    def home(self, key):
        if not isinstance(key, str) or not bizinfo.NOTICE_ID.fullmatch(key):
            raise ValueError("공고 번호를 확인해 주세요.")
        return self.path / key

    @lru_cache(maxsize=64)
    def store(self, key):
        return Store(self.home(key))

    def receipt(self, key):
        home = self.home(key)
        if not (home / "wiki.sqlite3").is_file():
            raise ValueError("먼저 공고 URL을 가져와 주세요.")
        store = self.store(key)
        with store.db() as db:
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='notice_import'"
            ).fetchone():
                row = db.execute(
                    "SELECT receipt FROM notice_import WHERE id=1"
                ).fetchone()
                if row:
                    return store, json.loads(row[0])
        raise ValueError("공고를 가져온 기록이 없습니다.")

    def list(self):
        out = []
        for path in sorted(self.path.glob("PBLN_*")):
            try:
                _, receipt = self.receipt(path.name)
                out.append({"id": path.name, "title": receipt["title"]})
            except ValueError:
                continue
        return out

    def team_decisions(self):
        entries = []
        for notice in self.list():
            store, _ = self.receipt(notice["id"])
            with store.db() as db:
                rows = db.execute("""SELECT d.id, d.topic, d.created, d.selection, t.status,
                    (d.id = (SELECT max(id) FROM decisions WHERE topic=d.topic)) AS latest
                    FROM decisions d JOIN topics t ON t.name=d.topic ORDER BY d.id DESC""")
                entries.extend(
                    {**dict(row), "notice": notice["id"], "title": notice["title"]}
                    for row in rows
                )
        return sorted(entries, key=lambda entry: entry["created"], reverse=True)

    def import_url(self, url):
        with self.lock:
            page, title, files = bizinfo.discover(url, self.read)
            key = parse_qs(urlsplit(page).query)["pblancId"][0]
            home = self.home(key)
            home.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=home) as staging:
                folder = Path(staging)
                receipt = self.prepare(page, title, files, home, folder)
                receipt["id"] = key
                receipt["revision"] = digest(pack(receipt))
                self.store(key).sync(folder, workspace=home, notice_receipt=receipt)
            return self.view(key)

    def prepare(self, page, title, files, home, folder):
        inventory, supplements, catalog = [], {}, []
        main, rules, total = None, {}, 0
        for f in files:
            role, reason = bizinfo.classify(title, f)
            row = {"name": f.name, "url": f.stable, "role": role, "status": reason}
            inventory.append(row)
            if role in ("제외", "참고"):
                continue
            is_root = role == "본문"
            if not f.name.lower().endswith((".pdf", ".hwpx")):
                if is_root:
                    raise ValueError("본문은 텍스트 PDF 또는 HWPX가 필요합니다.")
                row["status"] = "목록에서 발견. 이 파일 형식은 분석하지 않음"
                continue
            # Fail the whole refresh on network errors rather than replacing a
            # good edition with an incomplete attachment set.
            raw = self.read(f.signed, page, min(bizinfo.FILE_SIZE, (64 << 20) - total))
            total += len(raw)
            if total > 64 << 20:
                raise ValueError("공고 원본 합계가 64 MB를 넘었습니다.")
            checksum = hashlib.sha256(raw).hexdigest()
            row["raw_sha256"] = checksum
            raw_dir = home / "originals"
            raw_dir.mkdir(exist_ok=True)
            if not (raw_dir / checksum).exists():
                with tempfile.NamedTemporaryFile(dir=raw_dir, delete=False) as tmp:
                    tmp.write(raw)
                os.replace(tmp.name, raw_dir / checksum)
            try:
                parts = pages(raw, f.name, is_root)
            except ValueError as exc:
                if is_root:
                    raise
                row["status"] = str(exc)
                continue
            if not is_root and (mismatch := bizinfo.cover_conflict(title, parts)):
                row.update(role="제외", status=mismatch)
                continue
            row["status"] = "원문 추출"
            row["path"] = path = "공고.md" if is_root else digest(f.stable)[:24] + ".md"
            record = {
                "path": path,
                "publication": page,
                "url": f.stable,
                "program": title,
                "year": int(bizinfo.YEAR.search(title)[1]),
                "raw_sha256": checksum,
                "role": {"본문": "notice", "FAQ": "faq", "첨부": "attachment"}[role],
            }
            if is_root:
                main = record
                rules = root_rules(parts)
            else:
                supplements[path] = parts
                md = attachment_md(parts)
                if len(md.encode()) > 512_000:
                    row.pop("path")
                    row["status"] = "추출 본문이 512 KB를 넘어 분석하지 않음"
                    del supplements[path]
                    continue
                (folder / path).write_bytes(md.encode())
            catalog.append(record)
        if not main:
            raise ValueError("공고명과 연도가 일치하는 본문을 찾을 수 없습니다.")
        rule_terms = candidate_terms(rules, supplements.values())
        md = "\n".join(
            f"## {heading}\n{quote}\n" for heading, (_, quote) in rules.items()
        )
        (folder / main["path"]).write_bytes(md.encode())
        main.update(
            rule_terms=rule_terms,
            terms=sorted({t for ts in rule_terms.values() for t in ts}),
            companions=[r["url"] for r in catalog if r is not main],
        )
        for record in catalog:
            record["sha256"] = hashlib.sha256(
                (folder / record["path"]).read_bytes()
            ).hexdigest()
        (folder / "folio-sources.json").write_text(
            pack({"version": 1, "sources": catalog}), encoding="utf8"
        )
        return {
            "url": page,
            "title": title,
            "files": inventory,
            "locations": {head: pos for head, (pos, _) in rules.items()},
            "rule_terms": rule_terms,
        }

    def view(self, key):
        with self.lock:
            store, receipt = self.receipt(key)
            state = store.view()
            topics = []
            for t in state["topics"]:
                sel = next((c for c in t["candidates"] if c["path"] == "공고.md"), None)
                matches = (
                    store.preview(t["name"], t["generation"], sel["id"]) if sel else []
                )
                if not matches and t["status"] == "open":
                    continue
                decision = next(
                    (d for d in state["decisions"] if d["topic"] == t["name"]), None
                )
                topics.append(
                    {
                        "name": t["name"],
                        "generation": t["generation"],
                        "selection": sel["id"] if sel else None,
                        "quote": sel["quote"] if sel else "",
                        "matches": matches,
                        "status": t["status"],
                        "comparison": t["comparison"],
                        "last_confirmed": decision and decision["created"],
                    }
                )
            return {**receipt, "topics": topics}

    def confirm(self, key, revision, topic, generation):
        with self.lock:
            store, receipt = self.receipt(key)
            if receipt["revision"] != revision:
                raise Conflict("공고 판본이 바뀌었습니다. 다시 확인해 주세요.")
            item = next(
                (t for t in self.view(key)["topics"] if t["name"] == topic), None
            )
            if (
                not item
                or generation != item["generation"]
                or (not item["matches"] and item["status"] != "review_again")
            ):
                raise Conflict("현재 원문에서 연결 후보를 다시 확인해 주세요.")
            if item["status"] != "adopted":
                selection = item["selection"] if item["matches"] else "withdraw"
                store.decide(
                    topic,
                    generation,
                    selection,
                    "담당자",
                    "공고 본문과 첨부 원문 대조",
                    notice_revision=revision,
                )
            return self.view(key)

    def original(self, key, checksum):
        store, _ = self.receipt(key)
        with store.db() as db:
            item = db.execute(
                "SELECT name FROM notice_original WHERE sha=?", (checksum,)
            ).fetchone()
        if not item:
            raise KeyError("이 공고의 원본을 찾을 수 없습니다.")
        kind = (
            "application/pdf"
            if item["name"].lower().endswith(".pdf")
            else "application/octet-stream"
        )
        return (self.home(key) / "originals" / checksum).read_bytes(), kind
