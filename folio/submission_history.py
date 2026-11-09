"""Recover previously untracked fields only from an identifiable archived edition."""

import hashlib
import json

from . import hwp_notice, submission


def recover(db, directory):
    db.execute("""CREATE TABLE IF NOT EXISTS submission_baselines(
        url TEXT, version TEXT, conditions TEXT NOT NULL, PRIMARY KEY(url,version))""")
    old = db.execute("SELECT receipt FROM notice_import WHERE id=1").fetchone()
    if not old or not db.execute("SELECT 1 FROM decisions LIMIT 1").fetchone():
        return
    receipt = json.loads(old[0])
    if "submissions" in receipt:
        return
    snapshots = [json.loads(r[0]) for r in db.execute("SELECT bundles FROM snapshots")]
    for f in receipt["files"]:
        if not f.get("path") or not f["name"].lower().endswith(".hwp"):
            continue
        editions = [
            root["members"][f["path"]]
            for s in snapshots
            for root in s.values()
            if f["path"] in root["members"]
            and root["members"][f["path"]]["url"] == f["url"]
        ]
        current = json.loads(
            db.execute(
                "SELECT bundles FROM snapshots JOIN current ON snapshots.id=current.snapshot"
            ).fetchone()[0]
        )
        member = current.get("공고.md", {}).get("members", {}).get(f["path"])
        if not member or sum(m["version"] == member["version"] for m in editions) != 1:
            # Old stores didn't record raw IDs per decision. Two distinct raw
            # snapshots may have produced the same checklist Markdown.
            continue
        archive = directory / "originals" / f["raw_sha256"]
        try:
            raw = archive.read_bytes()
            if hashlib.sha256(raw).hexdigest() != f["raw_sha256"]:
                continue
            parts, rows = hwp_notice.read_blocks(hwp_notice.convert(raw))
        except (OSError, ValueError):
            continue
        submission.assign(rows, parts)
        data = {r["location"]: submission.conditions(r) for r in rows}
        db.execute(
            "INSERT OR IGNORE INTO submission_baselines VALUES (?,?,?)",
            (member["url"], member["version"], json.dumps(data, ensure_ascii=False)),
        )


def enrich(db, bundle):
    if not bundle.get("proof_targets"):
        return
    for m in bundle["members"].values():
        if "submission" in m:
            continue
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='submission_baselines'"
        ).fetchone():
            return
        row = db.execute(
            "SELECT conditions FROM submission_baselines WHERE url=? AND version=?",
            (m["url"], m["version"]),
        ).fetchone()
        if row:
            m["submission"] = json.loads(row[0])
