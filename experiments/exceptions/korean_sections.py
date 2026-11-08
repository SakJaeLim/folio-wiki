"""Replay the ministry's three pinned HWPX editions. Uses only the Python standard library."""

import argparse
import hashlib
import json
import re
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.corrections.sources import paragraphs  # noqa: E402
from folio.store import Store  # noqa: E402

EDITIONS = {
    "141": (
        "1065960",
        "f2a5dbcf-8a62-4ebf-9182-9f7df3022587",
        "9c4316d9b9582010fd7ed439a33c119a9dd2bc904264949db5661e47ed07930e",
    ),
    "281": (
        "1067487",
        "471a298b-1dac-4984-b2ff-04b88c5d2e81",
        "4424087cdd47ac3f1e9bddccb4521c7ee589aab91555dc51cda4cf9d5bbd0774",
    ),
    "287": (
        "1067495",
        "4a3e1b17-155f-4cce-a1aa-bf9f8d050877",
        "1f7c53ff468eb90ff5f21cd28cafc1a5675b0005817a79d4ca527e6b4a7bc0fe",
    ),
}
RULE = "Ⅲ. 유의사항 (융자제한기업)"
EXPORT = "Ⅳ. 사업별 정책자금 융자계획 / 2-2 수출기업글로벌화"
DOMESTIC = "Ⅳ. 사업별 정책자금 융자계획 / 2-1 내수기업수출기업화"
CASES = [
    ("expanded", "141", "281", EXPORT, "수출국 다변화 기업", "①", True),
    ("other-program", "141", "281", DOMESTIC, "수출국 다변화 기업", "①", False),
    ("existing-audience", "141", "281", EXPORT, "해외법인지원자금", "①", False),
    (
        "similar-name-control",
        "141",
        "281",
        EXPORT,
        "수출국 다변화 예정 기업",
        "①",
        False,
    ),
    ("other-rule", "141", "281", EXPORT, "수출국 다변화 기업", "③", False),
    ("budget-correction", "281", "287", EXPORT, "수출국 다변화 기업", "①", False),
]


def read_edition(key, corpus):
    bc, name, digest = EDITIONS[key]
    url = f"https://www.mss.go.kr/common/board/Download.do?bcIdx={bc}&cbIdx=310&streFileNm={name}.hwpx"
    if corpus:
        raw = (corpus / (key + ".hwpx")).read_bytes()
    else:
        with urllib.request.urlopen(url, timeout=40) as response:
            raw = response.read()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"{key}: official attachment has changed")
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        xml = sorted(
            (
                n
                for n in archive.namelist()
                if re.fullmatch(r"Contents/section\d+\.xml", n)
            ),
            key=lambda n: int(re.search(r"\d+", n)[0]),
        )
        pars = [p for n in xml for p in paragraphs(ET.fromstring(archive.read(n)))]
    lines, coords = ["# 정책자금 공고"], {}
    for i, p in enumerate(pars):
        if re.fullmatch(r"[Ⅰ-Ⅻ]+|\d+-\d+", p) and i + 1 < len(pars):
            level = "### " if "-" in p else "## "
            title = p + (" " if "-" in p else ". ") + pars[i + 1]
            lines += ["", level + title]
        lines += ["", p]
        coords[len(lines)] = i + 1
    return "\n".join(lines) + "\n", coords, pars


def run(out, corpus, baseline=False):
    out.mkdir(parents=True, exist_ok=False)
    editions = {k: read_edition(k, corpus) for k in EDITIONS}
    rows = []
    for case, old, new, program, audience, number, positive in CASES:
        directory = out / case
        src = directory / "source"
        src.mkdir(parents=True)
        notice = src / "공고.md"
        (src / "검토 질문.md").write_text(
            "## " + RULE + "\n이 기업에 융자 제한을 적용하는가?", encoding="utf8"
        )
        notice.write_text(editions[old][0], encoding="utf8")
        store = Store(directory / "state")
        store.sync(src)

        def topic():
            return next(t for t in store.view()["topics"] if t["name"] == RULE)

        original = topic()
        item = next(i for i in original["candidates"] if i["path"] == notice.name)
        unit = next(
            i
            for i, p in enumerate(item["units"])
            if p["quote"].startswith(number + " ")
        )
        anchor = item["units"][unit]
        kwargs = {} if baseline else dict(scope=program, audience=audience)
        store.decide(
            RULE,
            original["generation"],
            item["id"],
            "시험 담당자",
            f"{program} / {audience}",
            unit,
            **kwargs,
        )
        notice.write_text(editions[new][0], encoding="utf8")
        store.sync(src)
        actual = topic()
        row = dict(
            case=case,
            old=old,
            new=new,
            program=program,
            audience=audience,
            anchor_paragraph=editions[old][1][anchor["start"]],
            anchor_text=anchor["quote"],
            expected="review_again" if positive else "adopted",
            status=actual["status"],
            change=actual["comparison"],
        )
        if baseline:
            assert actual["status"] == "adopted"
        else:
            assert actual["status"] == row["expected"], case
            if positive:
                change = row["change"]
                assert (
                    change["before"]["quote"]
                    == change["after"]["quote"]
                    == anchor["quote"]
                )
                [evidence] = change["exceptions"]["added"]
                assert (
                    evidence["section"] == program
                    and evidence["quote"] in editions[new][0]
                )
                row["exception_paragraph"] = editions[new][1][evidence["start"]]
                assert (
                    row["exception_paragraph"] == 793
                    and evidence["quote"] == editions[new][2][792]
                )
                assert (
                    evidence["version"]
                    == hashlib.sha256(notice.read_bytes()).hexdigest()
                )
                stored = store.source(evidence["path"], evidence["version"])["body"]
                assert stored.splitlines()[evidence["start"] - 1] == evidence["quote"]
        rows.append(row)
        print(case, actual["status"])
    (out / "results.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--corpus", type=Path, help="Local verified 141.hwpx, 281.hwpx and 287.hwpx"
    )
    args = parser.parse_args()
    if args.out:
        run(args.out, args.corpus)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            run(Path(tmp) / "replay", args.corpus)
