"""Test one-field HWP revisions against approvals in an isolated notice store."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from experiments.exceptions.hwp_proof import PINS, START
from folio import bizinfo
from folio.notice_import import NoticeImports

RENT = "예외 · 부동산 임대업 보유자"
FOLLOWUP = "서류평가 통과자의 창업 여부 확인"
RENT_GROUP = "‘부동산 임대업 보유자 증빙서류’"
TIMING = (
    f", {RENT_GROUP}는 신청 시 제출하고, 서류평가 통과자에 한하여 ",
    f"는 신청 시 제출하고, 서류평가 통과자에 한하여 {RENT_GROUP}, ",
)
FORM_OPTION = (
    "4대 사회보험 가입자 명부 대체 가능\r",
    "4대 사회보험 가입자 명부 대체 불가\r",
)
ROW_OPTION = (
    "4대 사회보험 가입자 명부 대체 제출 가능",
    "4대 사회보험 가입자 명부 대체 제출 불가",
)
POST_TO_APPLY = (
    "’는 신청 시 제출하고, 서류평가 통과자에 한하여 ‘창업사실 확인서류’, ",
    "’, ‘창업사실 확인서류’는 신청 시 제출하고, 서류평가 통과자에 한하여 ",
)
SUBSTITUTE = (
    FORM_OPTION[0],
    "재직증명서".ljust(len("4대 사회보험 가입자 명부")) + " 대체 가능\r",
)
UNRELATED = ("본 페이지는 삭제 후 제출", "이 페이지는 삭제 후 제출")


def revise(raw, edit):
    cli = Path(shutil.which("kordoc")).resolve()
    if os.name == "nt":
        cli = cli.parent / "node_modules/kordoc/dist/cli.js"
    return subprocess.run(
        [
            shutil.which("node"),
            str(Path(__file__).with_name("revise_hwp.cjs")),
            str(cli),
            json.dumps([edit], ensure_ascii=False),
        ],
        input=raw,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout


def run(folder):
    page, title, files = bizinfo.discover(START)
    target = next(f for f in files if "증빙서류 제출목록" in f.name)
    cache = {}
    replacement = None

    def read(url, referer, limit):
        if url == page:
            if page not in cache:
                cache[page] = bizinfo.fetch(url, referer, limit)
            return cache[page]
        stable, _ = bizinfo.download_link(page, url)
        if stable == target.stable and replacement is not None:
            return replacement
        if stable not in cache:
            cache[stable] = bizinfo.fetch(url, referer, limit)
        return cache[stable]

    service = NoticeImports(folder, read)
    baseline = service.import_url(page)
    assert baseline["title"] == title
    raw = cache[target.stable]
    assert hashlib.sha256(raw).hexdigest() == PINS[page][0]
    assert (
        next(f for f in baseline["files"] if f["role"] == "본문")["raw_sha256"]
        == PINS[page][1]
    )
    slots = baseline["submissions"]
    assert [
        sum(r["stage"] == phase for r in slots)
        for phase in ("application", "after", "uncertain")
    ] == [6, 2, 1]
    assert {r["document"] for r in baseline["application_forms"]} == {
        "사업신청서",
        "사업계획서",
    }
    decisions = {t["name"] for t in baseline["topics"]}
    assert len(decisions) == 7
    for topic in baseline["topics"]:
        service.confirm(
            baseline["id"], baseline["revision"], topic["name"], topic["generation"]
        )

    results = []
    for label, edit, expected in [
        ("임대업 서류 제출 시점", TIMING, RENT),
        ("붙임 6의 대체 허용", FORM_OPTION, RENT),
        ("붙임 6의 대체 서류명", SUBSTITUTE, RENT),
        ("제출목록의 대체 허용", ROW_OPTION, RENT),
        ("창업사실 확인서류 제출 시점", POST_TO_APPLY, FOLLOWUP),
        ("편집 안내 문구", UNRELATED, None),
    ]:
        replacement = revise(raw, edit)
        assert replacement != raw
        view = service.import_url(page)
        reopened = {
            t["name"]: t for t in view["topics"] if t["status"] == "review_again"
        }
        assert set(reopened) == ({expected} if expected else set()), (
            label,
            list(reopened),
        )
        assert {
            t["name"] for t in view["topics"] if t["status"] == "adopted"
        } == decisions - set(reopened)
        if expected:
            diff = reopened[expected]["comparison"]["exceptions"]
            before = [m["submission"] for m in diff["removed"]]
            after = [m["submission"] for m in diff["added"]]
            if edit in (TIMING, POST_TO_APPLY):
                stages = {
                    "from": [m["stage"] for m in before],
                    "to": [m["stage"] for m in after],
                }
                assert set(stages["from"]) == {
                    "application" if edit == TIMING else "after"
                }
                assert set(stages["to"]) == {
                    "after" if edit == TIMING else "application"
                }
            else:
                assert any(
                    "가능" in a["quote"] for m in before for a in m["alternatives"]
                )
                assert any(
                    ("재직증명서" if edit == SUBSTITUTE else "불가") in a["quote"]
                    for m in after
                    for a in m["alternatives"]
                )
            retry = service.import_url(page)
            assert (
                retry["revision"] == view["revision"]
                and retry["topics"] == view["topics"]
            )
        results.append((label, list(reopened), len(decisions) - len(reopened)))
        replacement = None
        restored = service.import_url(page)
        assert restored["revision"] == baseline["revision"] and all(
            t["status"] == "adopted" for t in restored["topics"]
        )
    return results


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        for label, reopened, kept in run(Path(directory)):
            print(
                f"{label}: 재검토 {len(reopened)}건 {', '.join(reopened)} / 유지 {kept}건"
            )
