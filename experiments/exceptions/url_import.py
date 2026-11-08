"""Replay URL-only discovery, then introduce two unrelated real FAQ files locally."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from experiments.exceptions.notice_files import ASSETS, BIZ, fetch
from folio import bizinfo
from folio.notice_import import NoticeImports
from folio.notice_text import pages


def run(corpus):
    # Neither program nor terms nor file IDs are submitted to the importer.
    html = bizinfo.fetch(BIZ, BIZ, 2 << 20)
    added = {}
    names = {"faq25.pdf": "추가 FAQ.pdf", "other26.hwpx": "추가 FAQ.hwpx"}
    for index, (key, name) in enumerate(names.items(), 1):
        raw = fetch(key, corpus)
        assert hashlib.sha256(raw).hexdigest() == ASSETS[key][2]
        text = " ".join(" ".join(p.split()) for _, p in pages(raw, name))
        assert "가구, 기구 등은 사업비 집행이 불가합니다" in text
        # Even a plausible same-site listing entry and a neutral filename must
        # not override contradictory year/programme evidence on the cover.
        rel = f"/cmm/fms/fileDown.do?atchFileId=FILE_9&fileSn={index}"
        added[rel] = (name, raw)
    mixed = False
    cache = {}

    def read(url, ref, limit):
        if url != BIZ:
            for rel, (_, raw) in added.items():
                if url.endswith(rel):
                    return raw
            if url not in cache:
                cache[url] = bizinfo.fetch(url, ref, limit)
            return cache[url]
        if not mixed:
            return html
        rows = "".join(
            f'<li><div class="file_name">{name}</div><a class="icon_download" href="{rel}">다운로드</a></li>'
            for rel, (name, _) in added.items()
        )
        # Match the actual heading only inside the scoped official file list.
        marker = "<h3>첨부파일</h3>"
        source = html.decode()
        assert source.count(marker) == 1
        return source.replace(marker, marker + rows).encode()

    with tempfile.TemporaryDirectory() as temp:
        service = NoticeImports(temp, read)
        clean = service.import_url(BIZ)
        root = next(f for f in clean["files"] if f["role"] == "본문")
        faq = next(f for f in clean["files"] if f["role"] == "FAQ")
        assert (root["raw_sha256"], faq["raw_sha256"]) == (
            ASSETS["root26.pdf"][2],
            ASSETS["faq26.pdf"][2],
        )
        assert len(clean["files"]) == 6
        (topic,) = (
            t for t in clean["topics"] if t["name"] not in clean.get("proof_topics", [])
        )
        assert (
            clean["locations"][topic["name"]] == "PDF 2쪽"
            and "기계장치" in topic["name"]
        )
        assert topic["status"] == "open" and len(topic["matches"]) == 1
        assert topic["matches"][0]["section"] == "PDF 15쪽"
        assert "사무용 공간" in topic["matches"][0]["quote"]
        assert "시제품" in topic["matches"][0]["quote"]
        service.confirm(
            clean["id"], clean["revision"], topic["name"], topic["generation"]
        )
        mixed = True
        replay = service.import_url(BIZ)
        assert len(replay["files"]) == 8 and len(replay["topics"]) == len(
            clean["topics"]
        )
        checked = next(t for t in replay["topics"] if t["name"] == topic["name"])
        assert checked["matches"] == topic["matches"]
        assert checked["status"] == "adopted"
        rejected = [f for f in replay["files"] if f["role"] == "제외"]
        assert {f["raw_sha256"] for f in rejected} == {ASSETS[k][2] for k in names}
        return {
            "live_files": len(clean["files"]),
            "candidate": topic["name"],
            "rule": topic["quote"],
            "terms": clean["rule_terms"][topic["name"]],
            "faq": topic["matches"][0]["quote"],
            "negative_control_files": len(rejected),
            "excluded": [f["status"] for f in rejected],
            "spurious_reviews": 0,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Optional directory of the two pinned historical FAQ files",
    )
    print(json.dumps(run(parser.parse_args().corpus), ensure_ascii=False, indent=2))
