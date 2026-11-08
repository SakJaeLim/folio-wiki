"""Check two official HWP checklists against independently specified row assignments."""

import tempfile
from pathlib import Path

from folio import bizinfo
from folio.notice_import import NoticeImports

START = "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000119859"
EXPO = "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000119304"
PINS = {
    START: (
        "26feb7b5e4284ae1d8cc8fe805c01b29b457313267c982b4f590e99d09bd683d",
        "a752fc25a27439c34cea7259708f275510606bba7d88356f14005fc49ad724ea",
    ),
    EXPO: (
        "dba6ce12c5370fedb3ebea343e25264d39ceec61d77a648b6ca4dad3fbaada28",
        "2bb15d1ae9b108ebf39af60a2a14337d8fde75e7026a8f28925c8aa0f9a5a646",
    ),
}

# section of the notice, page, operative text in the notice, text in the checklist
START_ROWS = {
    2: ("필수 증빙", 7, "필수 증빙", "신분증 사본"),
    3: ("가점", 8, "대학원 졸업생", "대학원 졸업증명서 1부"),
    4: ("가점", 8, "장관급 이상", "입상실적 증명원 또는 상장 사본"),
    5: ("면제", 8, "만 39세 이하", "성실경영 심층평가 통과 확인증"),
    6: ("예외", 3, "직원을 고용하지 않고", "사업자등록증 사본"),
    7: ("예외", 3, "직원을 고용하지 않고", "건강보험자격득실확인서"),
}
EXPO_DOCS = (
    "신청서 및 신청내역",
    "개인정보활용동의서",
    "청렴이행 서약서",
    "사업자등록증",
    "중소기업확인서",
    "4대보험 사업장 가입자명부",
    "납입증명서",
    "재무제표",
    "공장등록증명서",
    "제품 홍보물",
    "특허 및 인증",
    "지정서",
)


def check(view, page, proof_hash):
    topics = [t for t in view["topics"] if t["name"] in view["proof_topics"]]
    numbered = {}
    for t in topics:
        for m in t["matches"]:
            f = next(f for f in view["files"] if f.get("path") == m["path"])
            assert f["raw_sha256"] == proof_hash and m["publication"] == page
            i = int(m["section"].split()[-1].removesuffix("행"))
            assert i not in numbered
            numbered[i] = t, m
    expected = (
        START_ROWS
        if page == START
        else {
            i: ("필수 제출서류" if i <= 9 else "기타 제출서류(보유 시)", 5, doc, doc)
            for i, doc in enumerate(EXPO_DOCS, 2)
        }
    )
    assert set(expected) == numbered.keys()
    for i, (group, physical_page, rule, doc) in expected.items():
        t, m = numbered[i]
        assert t["name"].startswith(group + " ·")
        assert view["locations"][t["name"]] == f"PDF {physical_page}쪽"
        assert rule in t["quote"] and doc in m["quote"]
    if page == START:
        (pending,) = view["proof_unresolved"]
        assert (
            pending["location"].endswith("8행")
            and "기타 증빙서류" in pending["category"]
        )
        assert any("서류평가 통과자" in n["text"] for n in view["proof_notes"])
    else:
        assert not view["proof_unresolved"]
        assert "법인인 경우" in numbered[5][0]["quote"]
        assert "보유 시" in numbered[13][0]["quote"]
    return len(numbered)


def main():
    blobs, swaps = {}, {}

    def read(url, referer, limit):
        if url != referer:
            stable, _ = bizinfo.download_link(referer, url)
            if stable in swaps:
                return swaps[stable]
            if stable not in blobs:
                blobs[stable] = bizinfo.fetch(url, referer, limit)
            return blobs[stable]
        return bizinfo.fetch(url, referer, limit)

    with tempfile.TemporaryDirectory() as tmp:
        imports = NoticeImports(Path(tmp) / "clean", read)
        files = {}
        for page in (START, EXPO):
            view = imports.import_url(page)
            proof_sha, root_sha = PINS[page]
            checklist = next(
                f for f in view["files"] if f.get("raw_sha256") == proof_sha
            )
            assert (
                next(f for f in view["files"] if f["role"] == "본문")["raw_sha256"]
                == root_sha
            )
            files[page] = checklist["url"]
            count = check(view, page, proof_sha)
            print(
                f"{view['title']}: {count}개 표 행 일치, 미연결 {len(view['proof_unresolved'])}건"
            )
        # Simulate the other publisher's genuine checklist being served at the
        # current checklist URL. Every legal positive from above must disappear.
        swaps.update(
            {files[START]: blobs[files[EXPO]], files[EXPO]: blobs[files[START]]}
        )
        mixed = NoticeImports(Path(tmp) / "swapped", read)
        for page in (START, EXPO):
            result = mixed.import_url(page)
            assert not result["proof_topics"]
            print(f"{result['title']}: 타 기관 HWP 교체 후 증빙 연결 0건")


if __name__ == "__main__":
    main()
