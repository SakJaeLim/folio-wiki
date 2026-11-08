import concurrent.futures
import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GG = "https://www.gg.go.kr"
JB = "https://www.jeonbuk.go.kr/board/"


def urls_jb(sid, file, menu, page):
    args = f"boardId=BBS_0000129&dataSid={sid}&menuCd=DOM_00000010200{menu}&orderBy=REGISTER_DATE%3ADESC%2CTMP_FIELD1%3ADESC&paging=ok&startPage={page}"
    return (
        JB + "view.jeonbuk?" + args,
        JB + "download.jeonbuk?" + args + f"&command=update&fileSid={file}",
    )


DATA = {
    "gg-old": (
        GG + "/bbs/boardView.do?bIdx=231607799&bsIdx=469&menuId=1547",
        GG + "/cmmn/download.do?idx=891575",
    ),
    "gg-new": (
        GG + "/bbs/boardView.do?bIdx=235736436&bsIdx=469&menuId=1547",
        GG + "/cmmn/download.do?idx=893173",
    ),
    "jb-old": urls_jb("665225", "401044", "003001", 33),
    "jb-new": urls_jb("665632", "401269", "005000", 25),
}
EXPECTED = {
    "gg-old": "d82f842e679b9f2e266765a63f64de0f89976a36cb55730690908ee9fe175c76",
    "gg-new": "a4157dd79302db136d72160291d38f2060fe509ca8b0da9dd74d2aa8e5bae72e",
    "jb-old": "f2d17b5fb6aea2b87b76bfe1b8abd5f357284c95eff322680fb72ecf1a7c5b5e",
    "jb-new": "41f8231938d97ab8684f97c1a5bca3a0cf8e80fe03fef9ee0ce94e4126532a19",
}


def paragraphs(node):
    # Flush surrounding paragraph fragments before/after a nested table cell.
    parts = []

    def flush():
        line = "".join(parts).strip()
        parts.clear()
        if line:
            lines.append(line)

    def walk(el):
        name = el.tag.rsplit("}", 1)[-1]
        if name == "p":
            flush()
        if name == "t":
            parts.append("".join(el.itertext()))
        else:
            for ch in el:
                walk(ch)
        if name == "p":
            flush()

    lines = []
    walk(node)
    flush()
    return lines


def fetch(k):
    site, url = DATA[k]
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Referer": site}
    )
    path = ROOT / "official" / (k + ".hwpx")
    if path.exists():
        body = path.read_bytes()
    else:
        with urllib.request.urlopen(req, timeout=18) as r:
            body = r.read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != EXPECTED[k]:
        raise ValueError(f"{k}: attachment differs from the tested official edition")
    if not path.exists():
        path.write_bytes(body)
    with zipfile.ZipFile(path) as z:
        files = sorted(
            (n for n in z.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n)),
            key=lambda n: int(re.search(r"\d+", n)[0]),
        )
        assert files
        lines = [p for f in files for p in paragraphs(ET.fromstring(z.read(f)))]
    output = path.with_suffix(".txt")
    output.write_text("\n".join(lines) + "\n", encoding="utf8")
    return dict(
        key=k,
        page=site,
        file=url,
        bytes=path.stat().st_size,
        sha256=digest,
        paragraphs=len(lines),
        text_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
    )


if __name__ == "__main__":
    (ROOT / "official").mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        result = list(pool.map(fetch, DATA))
    (ROOT / "official" / "manifest.json").write_text(
        json.dumps(result, indent=2), encoding="utf8"
    )
