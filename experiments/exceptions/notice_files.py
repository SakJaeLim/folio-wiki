"""Replay official notice files. pdftotext is needed only for this PDF experiment."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.corrections.sources import paragraphs  # noqa: E402
from folio.store import Store  # noqa: E402

BIZ = "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000119859"
PRIOR = "https://ipsi.cku.ac.kr/bbs/cku_kr/1202/355859/artclView.do"
OTHER = "https://www.mss.go.kr/site/smba/ex/bbs/View.do?bcIdx=1066114&cbIdx=310"
MSS = "https://www.mss.go.kr/site/smba/ex/bbs/View.do?bcIdx=1067487&cbIdx=310"
PROGRAM = "예비창업패키지"
PDF_ROOT = "2026/공고.md"
FAQ = "2026/FAQ.md"
PREVIOUS = "2025/FAQ.md"
OTHER_FAQ = "사내벤처/FAQ.md"
TITLE = "기계장치 (공구·기구, 비품, SW 등)"
ANCHOR = "사업 수행에 필요한 일정 횟수 또는 반영구적으로 사용 가능한 기계 또는 설비, 비품을 구매하는 비용"
MSS_TITLE = "정책우선도 평가"
ASSETS = {
    "root26.pdf": (
        BIZ,
        "FILE_000000000748111:1",
        "a752fc25a27439c34cea7259708f275510606bba7d88356f14005fc49ad724ea",
    ),
    "faq26.pdf": (
        BIZ,
        "FILE_000000000748112:5",
        "82e5c8e86a587d22e82864b6dbe015f529c403f22cfbcdfe9bfe3c9d22c9c874",
    ),
    "faq25.pdf": (
        PRIOR,
        "https://ipsi.cku.ac.kr/bbs/cku_kr/1202/143585/download.do",
        "73ee3848caf117593058d22b5b2d4d48932e4cef3ed6fe4dfbcf562acf99c11e",
    ),
    "other26.hwpx": (
        OTHER,
        "https://www.mss.go.kr/common/board/Download.do?bcIdx=1066114&cbIdx=310&streFileNm=f6dbb0ae-9f90-4089-9eb4-a53a527953d9.hwpx",
        "f0df6ce495f8220ab9c26cbacec67d3d891348c42f755085d752c3a7b73478d8",
    ),
    "281-0.hwpx": (
        MSS,
        "https://www.mss.go.kr/common/board/Download.do?bcIdx=1067487&cbIdx=310&streFileNm=471a298b-1dac-4984-b2ff-04b88c5d2e81.hwpx",
        "4424087cdd47ac3f1e9bddccb4521c7ee589aab91555dc51cda4cf9d5bbd0774",
    ),
    "281-1.hwpx": (
        MSS,
        "https://www.mss.go.kr/common/board/Download.do?bcIdx=1067487&cbIdx=310&streFileNm=384be17f-4278-45ee-9034-679840c5b654.hwpx",
        "d720b251c1b1ff57dc5b0681638984a68aa1960f74b4f8d5a0aef03d70a92d69",
    ),
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and (href := dict(attrs).get("href")):
            self.hrefs.append(href)


def original_url(key):
    page, ref, _ = ASSETS[key]
    if page != BIZ:
        return ref
    file_id, num = ref.split(":")
    return urljoin(page, f"/cmm/fms/fileDown.do?atchFileId={file_id}&fileSn={num}")


def fetch(key, corpus):
    page, ref, digest = ASSETS[key]
    if corpus is not None:
        data = (corpus / key).read_bytes()
    else:

        def read(url):
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": page}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()

        listing = Links()
        listing.feed(read(page).decode("utf8"))
        url = original_url(key)

        def matches(href):
            target = urljoin(page, href)
            if page != BIZ:
                return target == url
            query = parse_qs(urlsplit(target).query)
            file_id, num = ref.split(":")
            return (
                urlsplit(target).netloc == "www.bizinfo.go.kr"
                and urlsplit(target).path == "/cmm/fms/fileDown.do"
                and query.get("atchFileId") == [file_id]
                and query.get("fileSn") == [num]
            )

        link = next((h for h in listing.hrefs if matches(h)), None)
        if not link:
            raise ValueError(f"{key}: attachment missing from official listing")
        data = read(urljoin(page, link))
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"{key}: original edition changed")
    return data


def hwpx(raw):
    with zipfile.ZipFile(BytesIO(raw)) as z:
        names = sorted(
            (n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
            key=lambda n: int(re.search(r"\d+", n)[0]),
        )
        return [p for n in names for p in paragraphs(ET.fromstring(z.read(n)))]


def pdf_pages(raw, mode):
    output = subprocess.run(
        ["pdftotext", mode, "-enc", "UTF-8", "-", "-"],
        input=raw,
        capture_output=True,
        check=True,
    ).stdout
    return output.decode("utf8").rstrip("\f").split("\f")


def documents(corpus):
    raw = {k: fetch(k, corpus) for k in ASSETS}
    main_pages = pdf_pages(raw["root26.pdf"], "-raw")
    page = " ".join(main_pages[1].split())
    assert TITLE in page and ANCHOR in page
    assert all(
        "사무용 공간에 들어가는 집기" not in " ".join(p.split()) for p in main_pages
    )
    texts = {PDF_ROOT: f"# 예비창업패키지 공고 2쪽\n## {TITLE}\n{ANCHOR}\n"}
    for k, path in (("faq26.pdf", FAQ), ("faq25.pdf", PREVIOUS)):
        texts[path] = "\n".join(
            f"## PDF {i}쪽\n"
            + "\n\n".join(line.strip() for line in p.splitlines() if line.strip())
            for i, p in enumerate(pdf_pages(raw[k], "-layout"), 1)
        )
    other = hwpx(raw["other26.hwpx"])
    texts[OTHER_FAQ] = "## 사내벤처 주요 질의응답\n" + "\n\n".join(other)
    for path in (FAQ, PREVIOUS, OTHER_FAQ):
        assert (
            "사무용 공간에 들어가는 집기, 가구, 기구 등은 사업비 집행이 불가합니다"
            in texts[path]
        )
    main = hwpx(raw["281-0.hwpx"])
    extra = hwpx(raw["281-1.hwpx"])
    assert (
        "정책우선도 평가를 통해" in main[175] and "정책우선도 평가 면제" in extra[2143]
    )
    texts["정책자금/본문.md"] = f"## {MSS_TITLE}\n{main[175]}\n"
    texts["정책자금/참고자료.md"] = "## 참고 14 AX 스프린트 우대트랙\n" + "\n\n".join(
        extra[2132:2146]
    )
    return texts


def registry(texts):
    def entry(path, key, role, year, program, **kwargs):
        return dict(
            path=path,
            role=role,
            publication=ASSETS[key][0],
            url=original_url(key),
            year=year,
            program=program,
            sha256=hashlib.sha256(texts[path].encode()).hexdigest(),
            **kwargs,
        )

    return {
        "version": 1,
        "sources": [
            entry(
                PDF_ROOT,
                "root26.pdf",
                "notice",
                2026,
                PROGRAM,
                terms=["기구"],
                companions=[original_url("faq26.pdf")],
            ),
            entry(FAQ, "faq26.pdf", "faq", 2026, PROGRAM),
            entry(PREVIOUS, "faq25.pdf", "faq", 2025, PROGRAM),
            entry(
                OTHER_FAQ,
                "other26.hwpx",
                "faq",
                2026,
                "예비창업패키지(특화분야) 사내벤처 육성",
            ),
            entry(
                "정책자금/본문.md",
                "281-0.hwpx",
                "notice",
                2026,
                "중소기업 정책자금",
                terms=[MSS_TITLE],
                companions=[original_url("281-1.hwpx")],
            ),
            entry(
                "정책자금/참고자료.md",
                "281-1.hwpx",
                "attachment",
                2026,
                "중소기업 정책자금",
            ),
        ],
    }


def run(out, corpus):
    texts = documents(corpus)
    out.mkdir(parents=True, exist_ok=False)
    records = []
    for name, root, title, added, expected in [
        ("listed-faq", PDF_ROOT, TITLE, [FAQ], True),
        ("previous-year", PDF_ROOT, TITLE, [PREVIOUS], False),
        ("similar-program", PDF_ROOT, TITLE, [OTHER_FAQ], False),
        ("mixed-folder", PDF_ROOT, TITLE, [PREVIOUS, OTHER_FAQ, FAQ], True),
        (
            "separate-annex",
            "정책자금/본문.md",
            MSS_TITLE,
            ["정책자금/참고자료.md"],
            True,
        ),
    ]:
        directory = out / name
        folder = directory / "source"
        folder.mkdir(parents=True)

        def install(path):
            target = folder / path
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_bytes(texts[path].encode())

        install(root)
        (folder / "팀 질문.md").write_text(
            f"## {title}\n적용할 기준을 확인합니다.", encoding="utf8"
        )
        (folder / "folio-sources.json").write_text(
            json.dumps(registry(texts), ensure_ascii=False), encoding="utf8"
        )
        store = Store(directory / "state")
        store.sync(folder)

        def topic():
            return next(t for t in store.view()["topics"] if t["name"] == title)

        t = topic()
        selected = next(s for s in t["candidates"] if s["path"] == root)
        store.decide(
            title, t["generation"], selected["id"], "시험 담당자", "공식 공고의 기준", 0
        )
        for path in added:
            install(path)
        store.sync(folder)
        t = topic()
        assert t["status"] == ("review_again" if expected else "adopted"), name
        if expected:
            result = t["comparison"]
            assert (
                result["external"]
                and result["before"]["version"] == result["after"]["version"]
            )
            [source] = result["exceptions"]["added"]
            assert source["path"] == added[-1]
            body = store.source(source["path"], source["version"])["body"]
            assert (
                source["quote"]
                == "\n".join(
                    body.splitlines()[source["start"] - 1 : source["end"]]
                ).strip()
            )
        records.append(dict(case=name, status=t["status"], comparison=t["comparison"]))
        print(name, t["status"])
    (out / "results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        run(args.out, args.corpus)
    else:
        with tempfile.TemporaryDirectory() as temp:
            run(Path(temp) / "replay", args.corpus)
