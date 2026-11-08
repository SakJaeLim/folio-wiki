"""python domestic.py --folio PATH --out NEW_DIRECTORY"""

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

from sources import ROOT


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")


def markdown(paras, cases):
    lines = ["# 공고 원문"]
    offsets = {}
    for i, paragraph in enumerate(paras, 1):
        for _, name, pattern, *_ in cases:
            if re.search(pattern, paragraph):
                lines.extend(("", f"## {name}"))
        lines.append("")
        lines.append(paragraph)
        offsets[len(lines)] = i
    return "\n".join(lines) + "\n", offsets


def run(repo, output):
    sys.path.insert(0, str(repo.resolve()))
    from folio.store import Store

    design = json.loads((ROOT / "domestic-protocol.json").read_text(encoding="utf8"))
    manifest = json.loads(
        (ROOT / "official" / "manifest.json").read_text(encoding="utf8")
    )
    for doc in manifest:
        for ext, field in (("hwpx", "sha256"), ("txt", "text_sha256")):
            assert (
                hashlib.sha256(
                    (ROOT / "official" / (doc["key"] + "." + ext)).read_bytes()
                ).hexdigest()
                == doc[field]
            )
    output.mkdir(exist_ok=False)
    all_results = {}
    for org in ("jb", "gg"):
        cases = [c for c in design["cases"] if c[0] == org]
        old, new = [
            (ROOT / "official" / f"{org}-{stage}.txt")
            .read_text(encoding="utf8")
            .splitlines()
            for stage in ("old", "new")
        ]
        folder = output / org / "source"
        folder.mkdir(parents=True)
        store = Store(output / org / "state")
        path = folder / "공고.md"
        notes = folder / "검토 질문.md"
        notes.write_text(
            "\n".join(f"## {c[1]}\n{c[-1]}" for c in cases), encoding="utf8"
        )
        before, old_offsets = markdown(old, cases)
        after, new_offsets = markdown(new, cases)
        path.write_text(before, encoding="utf8")
        store.sync(folder)
        ledger = []
        for _, name, _, original_line, needle, expected, question in cases:
            t = next(t for t in store.view()["topics"] if t["name"] == name)
            x = next(c for c in t["candidates"] if c["path"] == path.name)
            matches = [
                (i, u)
                for i, u in enumerate(x["units"])
                if old_offsets.get(u["start"]) == original_line and needle in u["quote"]
            ]
            assert len(matches) == 1, (name, original_line, matches)
            index, unit = matches[0]
            note = f"업무 질문 «{question}»에 적용할 공고 문장"
            store.decide(name, t["generation"], x["id"], "시험 담당자", note, index)
            ledger.append(
                dict(
                    topic=name,
                    old_paragraph=original_line,
                    old_quote=unit["quote"],
                    reason=note,
                    expected=expected,
                )
            )
        path.write_text(after, encoding="utf8")
        store.sync(folder)
        # Ordinary comparison has the exact same originals and starting decision ledger.
        diff = [
            op
            for op in difflib.SequenceMatcher(
                None, old, new, autojunk=False
            ).get_opcodes()
            if op[0] != "equal"
        ]
        (output / org / "full.diff").write_text(
            "\n".join(difflib.unified_diff(old, new, "old", "new", lineterm="")),
            encoding="utf8",
        )
        view = store.view()
        for record in ledger:
            task = next(t for t in view["topics"] if t["name"] == record["topic"])
            idx = record["old_paragraph"] - 1
            record["diff_changed"] = any(i <= idx < j for _, i, j, _, _ in diff)
            record["folio_changed"] = task["status"] == "review_again"
            record["comparison"] = task["comparison"]
            if record["folio_changed"]:
                change = task["comparison"]
                for side, offsets, paragraphs in (
                    ("before", old_offsets, old),
                    ("after", new_offsets, new),
                ):
                    item = change[side]
                    assert item["quote"] in paragraphs[offsets[item["start"]] - 1]
                    assert (
                        item["quote"]
                        in store.source(item["path"], item["version"])["body"]
                    )
                    record[side + "_paragraph"] = offsets[item["start"]]
            assert (
                record["expected"] == record["diff_changed"] == record["folio_changed"]
            ), record
        all_results[org] = dict(
            ledger=ledger,
            change_groups=len(diff),
            changed_old_paragraphs=sum(j - i for _, i, j, _, _ in diff),
            changed_new_paragraphs=sum(l - k for _, _, _, k, l in diff),
        )
    save(output / "domestic-results.json", all_results)
    print(
        [
            (
                org,
                sum(r["folio_changed"] for r in item["ledger"]),
                item["change_groups"],
            )
            for org, item in all_results.items()
        ]
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--folio", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    run(args.folio, args.out)
