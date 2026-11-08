import tempfile
import unittest
from pathlib import Path

from folio.store import Conflict, Store


class CrossSectionDecision(unittest.TestCase):
    title = "Ⅲ. 지원 제한"
    rule = "① 지원 제한 중 보증금 기준"
    citation = "Ⅲ. 지원 제한 ①항(보증금) 적용 예외"
    clause = "수출기업은 " + citation

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.folder = self.root / "data"
        self.folder.mkdir()
        self.file = self.folder / "공고.md"
        self.store = Store(self.root / "state")
        self.base = f"## {self.title}\n{self.rule}\n\n② 인지세 기준\n\n## 수출사업\n수출 지침입니다.\n\n## 내수사업\n내수 지침입니다."
        (self.folder / "질문.md").write_text(
            f"## {self.title}\n어떤 기준을 적용하는가?", encoding="utf8"
        )
        self.sync(self.base)

    def topic(self):
        return next(t for t in self.store.view()["topics"] if t["name"] == self.title)

    def sync(self, text):
        self.file.write_text(text, encoding="utf8")
        self.store.sync(self.folder)
        return self.topic()

    def adopt(self, scope="", audience="", unit=0):
        t = self.topic()
        source = next(c for c in t["candidates"] if c["path"] == self.file.name)
        self.store.decide(
            t["name"],
            t["generation"],
            source["id"],
            "시험",
            "적용 근거",
            unit,
            scope,
            audience,
        )

    def export(self, clause):
        return self.base.replace("수출 지침입니다.", "수출 지침입니다.\n\n" + clause)

    def test_lifecycle_and_sources(self):
        self.adopt("수출사업", "수출기업")
        new = self.export(self.clause)
        t = self.sync(new)
        self.assertEqual(t["status"], "review_again")
        added = t["comparison"]["exceptions"]["added"][0]
        self.assertEqual(added["section"], "수출사업")
        original = self.store.source(added["path"], added["version"])["body"]
        self.assertEqual(original.splitlines()[added["start"] - 1], self.clause)
        self.assertEqual(self.sync(new)["generation"], t["generation"])
        self.adopt("수출사업", "수출기업")
        extended = self.export("수출기업, 신규기업은 " + self.citation)
        self.assertEqual(self.sync(extended)["status"], "adopted")
        removed = self.sync(self.base)["comparison"]["exceptions"]["removed"][0]
        self.assertEqual(removed["quote"], self.clause)
        self.assertEqual(self.sync(new)["status"], "adopted")

    def test_nonmatching_reference_scope_and_target(self):
        self.adopt("수출사업", "수출기업")
        controls = [
            self.base + "\n\n" + self.clause,
            self.export(self.clause.replace("수출기업은", "예비수출기업은")),
            self.export(self.clause.replace("Ⅲ.", "Ⅳ.")),
            self.export(self.clause.replace("①항", "②항")),
            self.export(self.clause.replace("(보증금)", "(인지세)")),
            self.export("수출기업은 보증금 적용 예외"),
            self.export(self.clause + "가 아님"),
            self.export("수출기업은 일반 기준을 따르고, 내수기업은 " + self.citation),
            self.export("<!--\n" + self.clause + "\n-->"),
            self.export("\x60\x60\x60\n" + self.clause + "\n\x60\x60\x60"),
            self.export("> " + self.clause),
        ]
        for body in controls:
            with self.subTest(body=body):
                self.assertEqual(self.sync(body)["status"], "adopted")

    def test_global_decision_and_whole_section_include_second_number(self):
        self.adopt(unit=None)
        t = self.sync(self.export("다른기업은 Ⅲ. 지원 제한 ②항(인지세) 적용 제외"))
        self.assertEqual(t["status"], "review_again")

    def test_markdown_fragment_and_ambiguous_heading(self):
        base = self.base.replace("② 인지세 기준", "")
        self.sync(base)
        self.adopt()
        n = base.replace(
            "내수 지침입니다.", "참여기업은 [보증금](#ⅲ-지원-제한) 적용 예외"
        )
        self.assertEqual(self.sync(n)["status"], "review_again")
        # A duplicated destination name cannot identify the intended section.
        self.assertIsNone(
            self.sync(n + "\n## 부록\n### " + self.title + "\n별도 기준.")["comparison"]
        )

    def test_legacy_snapshot_is_reassessed_without_edit(self):
        self.adopt()
        t = self.sync(self.export(self.clause))
        with self.store.db() as db:
            db.execute("PRAGMA user_version=2")
            db.execute(
                "UPDATE topics SET comparison=NULL,status='adopted' WHERE name=?",
                (self.title,),
            )
        self.store = Store(self.root / "state")
        self.store.sync(self.folder)
        self.assertEqual(self.topic()["comparison"], t["comparison"])
        self.assertEqual(len(self.store.view()["decisions"]), 1)

    def test_scope_is_validated_before_decision_is_saved(self):
        with self.assertRaises(Conflict):
            self.adopt("존재하지 않는 절", "수출기업")
        self.assertEqual(self.store.view()["decisions"], [])
