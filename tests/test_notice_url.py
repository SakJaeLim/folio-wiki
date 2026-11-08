"""Exercise the ordinary import/confirm paths offline with valid HWPX files."""

import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape

from folio import bizinfo
from folio.notice_import import NoticeImports
from folio.store import Conflict

PAGE = "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000001123"
TITLE = "2026년 장비활용 바우처 공고"


def hwpx(lines):
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        xml = "".join(f"<hp:p><hp:t>{escape(s)}</hp:t></hp:p>" for s in lines)
        z.writestr("Contents/section0.xml", f'<s xmlns:hp="urn:hp">{xml}</s>')
    return out.getvalue()


def li(i, name):
    return (
        f'<li><div class="file_name">{escape(name)}</div><a class="icon_download" '
        f'href="/cmm/fms/fileDown.do?atchFileId=FILE_123&amp;fileSn={i}&amp;downloadToken=ephemeral">다운로드</a></li>'
    )


def listing(rows):
    return (
        f'<div class="support_project_detail"><h2 class="title">{TITLE}</h2>'
        '<div class="attached_file_list"><ul><h3>첨부파일</h3>'
        + "".join(li(i, name) for i, name in rows)
        + "<h3>본문출력파일</h3>"
        + li(1, TITLE + ".hwpx")
        + "</ul></div></div>"
        + "<aside>"
        + li(9, "다른 공고 FAQ.hwpx")
        + "</aside>"
    ).encode()


class NoticeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.files = {
            1: hwpx(["측정장비", "• 실험에 필요한 장비를 구매하는 비용"]),
            2: hwpx(
                [
                    "2026년 장비활용 바우처 질의응답",
                    "측정장비는 개인 용도로 구매 불가합니다.",
                ]
            ),
        }
        self.rows = [(2, "FAQ.hwpx")]
        self.fetched = []

        def read(url, _, size):
            if url == PAGE:
                return listing(self.rows)
            n = int(bizinfo.parse_qs(bizinfo.urlsplit(url).query)["fileSn"][0])
            self.fetched.append(n)
            return self.files[n]

        self.service = NoticeImports(self.dir, read)

    def run_import(self):
        return self.service.import_url(PAGE)

    def confirm(self, d):
        t = d["topics"][0]
        return self.service.confirm(d["id"], d["revision"], t["name"], t["generation"])

    def test_discovery_approval_restart_and_recheck(self):
        d = self.run_import()
        self.assertEqual(len(d["topics"]), 1)
        t = d["topics"][0]
        self.assertEqual(d["rule_terms"][t["name"]], ["측정장비"])
        self.assertEqual(t["status"], "open")
        self.assertIn("개인 용도", t["matches"][0]["quote"])
        self.assertEqual(self.fetched, [2, 1])
        self.assertNotIn("ephemeral", str(d))
        self.confirm(d)
        d2 = self.run_import()
        self.assertEqual(d["revision"], d2["revision"])
        self.assertEqual(d2["topics"][0]["status"], "adopted")
        self.confirm(d2)  # retry does not write another decision
        store, _ = NoticeImports(self.dir).receipt(d["id"])
        self.assertEqual(len(store.view()["decisions"]), 1)
        self.assertEqual(self.service.team_decisions()[0]["status"], "adopted")
        old = self.files[2]
        self.files[2] = hwpx(
            [
                "2026년 장비활용 바우처 질의응답",
                "측정장비는 해외 용도로 구매 불가합니다.",
            ]
        )
        revised = self.run_import()
        self.assertEqual(revised["topics"][0]["status"], "review_again")
        with self.assertRaises(Conflict):
            self.confirm(d)
        self.assertEqual(
            self.service.original(d["id"], d["files"][0]["raw_sha256"])[0], old
        )
        self.confirm(revised)
        self.rows = []
        removed = self.run_import()
        self.assertEqual(removed["topics"][0]["status"], "review_again")
        self.confirm(removed)
        self.assertEqual(store.view()["decisions"][0]["selection"], "withdraw")

    def test_names_covers_and_unlisted_files(self):
        self.rows += [
            (3, "2025년도 FAQ.hwpx"),
            (4, "사내벤처 FAQ.hwpx"),
            (5, "추가 FAQ.hwpx"),
            (6, "모집 FAQ.hwpx"),
            (7, "신청서 양식.hwp"),
            (8, "증빙.hwp"),
        ]
        for i, heading in [(5, "’25년 장비활용 바우처"), (6, "26년 사내벤처")]:
            self.files[i] = hwpx(
                [heading + " 주요 질의응답", "측정장비는 개인 용도로 구매 불가합니다."]
            )
        d = self.run_import()
        self.assertEqual([f["role"] for f in d["files"]].count("제외"), 4)
        self.assertEqual(len(d["topics"][0]["matches"]), 1)
        self.assertEqual(self.fetched, [2, 5, 6, 1])
        self.assertIn("분석하지 않음", d["files"][-2]["status"])
        self.assertEqual(len(d["files"]), 8)

    def test_negative_wording_and_unrelated_topics(self):
        self.files[2] = hwpx(
            [
                "측정장비는 구매 불가 대상이 아닙니다.",
                "측정장비 지원 가능합니다.",
                "다른 장비는 구매 불가합니다.",
            ]
        )
        self.assertFalse(self.run_import()["topics"])

    def test_bad_refresh_preserves_decision(self):
        d = self.run_import()
        self.confirm(d)
        self.files[1] = b"broken zip"
        with self.assertRaises(ValueError):
            self.run_import()
        self.assertEqual(self.service.view(d["id"])["topics"][0]["status"], "adopted")

    def test_url_bounds(self):
        for url in (
            PAGE.replace("www.bizinfo.go.kr", "127.0.0.1"),
            PAGE.replace("https:", "http:"),
            PAGE + "&pblancId=123",
            PAGE.replace("www.", "user@www."),
        ):
            with self.assertRaises(ValueError):
                bizinfo.notice_url(url)
        self.assertIsNone(bizinfo.download_link(PAGE, "https://example.org/file.pdf"))
        self.assertIsNone(
            bizinfo.download_link(
                PAGE, "/cmm/fms/fileDown.do?fileSn=1&atchFileId=FILE_1&redirect=x"
            )
        )

    def test_pdf_dependency_error(self):
        from folio.notice_text import pages

        with (
            patch("folio.notice_text.subprocess.run", side_effect=FileNotFoundError),
            self.assertRaisesRegex(ValueError, "pdftotext"),
        ):
            pages(b"%PDF-no-converter", "본문.pdf", True)
