import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from folio.store import Conflict, Store


class NoticeFiles(unittest.TestCase):
    rule = "기구 구매 기준"
    anchor = "사업에 필요한 기구를 구매할 수 있습니다."
    limit = "사무용 기구 구매는 불가합니다."
    url = "https://example.org/notices/26"
    child_url = "https://example.org/files/faq.pdf"

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = self.root / "source"
        self.folder.mkdir()
        self.main = self.folder / "notice.md"
        self.faq = self.folder / "FAQ.md"
        self.main.write_text(
            f"## {self.rule}\n{self.anchor}\n\n## 수출사업\n사업 안내", encoding="utf8"
        )
        (self.folder / "team.md").write_text(
            f"## {self.rule}\n무엇을 구매할 수 있는가?", encoding="utf8"
        )
        self.bytes = ("## 질문 4\n" + self.limit).encode()
        self.parent = dict(
            path="notice.md",
            role="notice",
            url=self.url + "/document",
            publication=self.url,
            year=2026,
            program="지원사업",
            sha256=self.hash(self.main.read_bytes()),
            companions=[self.child_url],
            terms=["기구"],
        )
        self.child = dict(
            path="FAQ.md",
            role="faq",
            url=self.child_url,
            publication=self.url,
            year=2026,
            program="지원사업",
            sha256=self.hash(self.bytes),
        )
        self.store = Store(self.root / "state")
        self.catalog()
        self.sync()

    @staticmethod
    def hash(data):
        return hashlib.sha256(data).hexdigest()

    def catalog(self):
        (self.folder / "folio-sources.json").write_text(
            json.dumps(dict(version=1, sources=[self.parent, self.child])),
            encoding="utf8",
        )

    def topic(self):
        return next(t for t in self.store.view()["topics"] if t["name"] == self.rule)

    def sync(self):
        self.store.sync(self.folder)
        return self.topic()

    def adopt(self, **kwargs):
        t = self.topic()
        c = next(c for c in t["candidates"] if c["path"] == self.main.name)
        self.store.decide(
            t["name"], t["generation"], c["id"], "검토자", "구매 기준", 0, **kwargs
        )

    def test_add_readopt_remove_restore_and_archive(self):
        self.adopt()
        self.faq.write_bytes(self.bytes)
        t = self.sync()
        proof = t["comparison"]["exceptions"]["added"][0]
        self.assertEqual(
            (t["status"], proof["path"], proof["start"], proof["publication"]),
            ("review_again", "FAQ.md", 2, self.url),
        )
        self.assertEqual(self.sync()["generation"], t["generation"])
        self.adopt()
        self.faq.unlink()
        lost = self.sync()["comparison"]
        self.assertEqual(lost["exceptions"]["removed"], [proof])
        self.assertIn(
            self.limit, self.store.source(proof["path"], proof["version"])["body"]
        )
        self.faq.write_bytes(self.bytes)
        self.assertEqual(self.sync()["status"], "adopted")

    def test_existing_attachment_can_be_read_before_adoption(self):
        self.faq.write_bytes(self.bytes)
        topic = self.sync()
        selected = next(x for x in topic["candidates"] if x["path"] == self.main.name)
        matches = self.store.preview(
            topic["name"], topic["generation"], selected["id"], 0
        )
        self.assertEqual([m["quote"] for m in matches], [self.limit])
        self.assertEqual(self.store.view()["decisions"], [])
        self.adopt()
        saved = next(
            x
            for x in self.store.view()["decisions"][0]["evidence"]
            if x["id"] == selected["id"]
        )
        self.assertEqual(saved["companion_evidence"], matches)
        self.assertEqual(self.sync()["status"], "adopted")

    def test_new_attachment_invalidates_an_open_form(self):
        prior = self.topic()
        selected = next(c for c in prior["candidates"] if c["path"] == self.main.name)
        self.faq.write_bytes(self.bytes)
        self.sync()
        with self.assertRaises(Conflict):
            self.store.decide(
                prior["name"],
                prior["generation"],
                selected["id"],
                "검토자",
                "늦은 제출",
                0,
            )
        self.assertEqual(self.store.view()["decisions"], [])

    def test_each_identity_gate_and_catalog_only_refresh(self):
        self.adopt()
        self.faq.write_bytes(self.bytes)
        for key, value in (
            ("year", 2025),
            ("program", "지원사업 특화"),
            ("publication", self.url + "-other"),
            ("url", self.child_url + "-other"),
        ):
            with self.subTest(key=key):
                old = self.child[key]
                self.child[key] = value
                self.catalog()
                self.assertEqual(self.sync()["status"], "adopted")
                self.child[key] = old
        self.catalog()
        self.assertEqual(self.sync()["status"], "review_again")

    def test_corrupt_file_does_not_replace_last_good_state(self):
        self.adopt()
        self.faq.write_bytes(self.bytes)
        self.sync()
        previous = self.store.view()
        self.faq.write_bytes(b"wrong edition")
        with self.assertRaises(ValueError):
            self.sync()
        self.assertEqual(previous, self.store.view())

    def test_unrelated_change_to_known_faq_is_quiet(self):
        self.faq.write_bytes(self.bytes)
        self.sync()
        self.adopt()
        other = self.bytes + b"\n\n## Calendar\nThe calendar has changed."
        self.faq.write_bytes(other)
        self.child["sha256"] = self.hash(other)
        self.catalog()
        self.assertEqual(self.sync()["status"], "adopted")

    def test_no_registration_and_first_registration_of_adopted_bytes(self):
        (self.folder / "folio-sources.json").unlink()
        self.sync()
        self.adopt()
        self.faq.write_bytes(self.bytes)
        self.assertEqual(self.sync()["status"], "adopted")
        self.catalog()
        self.assertEqual(self.sync()["status"], "review_again")
        self.store = Store(self.root / "state")
        self.child["year"] = self.parent["year"] = 2025
        self.catalog()
        self.assertEqual(self.sync()["status"], "adopted")

    def test_previous_scope_and_audience(self):
        self.adopt(scope="수출사업", audience="수출기업")
        self.child["scope"] = "내수사업"
        raw = ("## 질문 2\n수출기업은 기구 구매가 불가합니다.").encode()
        self.child["sha256"] = self.hash(raw)
        self.faq.write_bytes(raw)
        self.catalog()
        self.assertEqual(self.sync()["status"], "adopted")
        self.child["scope"] = "수출사업"
        self.catalog()
        self.assertEqual(self.sync()["status"], "review_again")

    def test_similar_term_or_different_cost_is_quiet(self):
        self.adopt()
        text = "## 질문 1\n연구기구 구매는 불가합니다.\n\n기구 구매는 가능하지만 인건비 지급은 불가합니다."
        raw = text.encode()
        self.child["sha256"] = self.hash(raw)
        self.faq.write_bytes(raw)
        self.catalog()
        self.assertEqual(self.sync()["status"], "adopted")

    def test_numbered_citation_in_attachment_without_terms(self):
        self.rule = "Ⅲ. 구매 제한"
        self.main.write_text(
            f"## {self.rule}\n① 영리기업의 보증금 기준", encoding="utf8"
        )
        (self.folder / "team.md").write_text(
            f"## {self.rule}\n제한 확인", encoding="utf8"
        )
        self.parent.update(sha256=self.hash(self.main.read_bytes()), terms=[])
        self.child["role"] = "attachment"
        self.catalog()
        self.sync()
        self.adopt()
        for number, status in (("②", "adopted"), ("①", "review_again")):
            raw = f"## 대상\n신규기업은 Ⅲ. 구매 제한 {number}항(보증금) 적용 예외".encode()
            self.faq.write_bytes(raw)
            self.child["sha256"] = self.hash(raw)
            self.catalog()
            self.assertEqual(self.sync()["status"], status)

    def test_plain_faq_retains_original_line(self):
        self.adopt()
        body = ("# FAQ\n\n" + self.limit).encode()
        self.child["sha256"] = self.hash(body)
        self.faq.write_bytes(body)
        self.catalog()
        evidence = self.sync()["comparison"]["exceptions"]["added"][0]
        self.assertEqual((evidence["start"], evidence["quote"]), (3, self.limit))
