import json
import tempfile
import unittest
from pathlib import Path

from folio.store import Conflict, Store


class AnchoredDecision(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.folder = root/"docs"
        self.folder.mkdir()
        self.state = root/"state"
        self.store = Store(self.state)
        self.notice = self.folder/"notice.md"
        self.original = "# 지원사업\n## 접수\n방문 접수합니다. [신청][form]을 이용합니다.\n\n## 참고\n[form]: https://example.org/v1\n[other]: https://example.org/unrelated\n"
        self.notice.write_text(self.original, encoding="utf8")
        (self.folder/"guide.md").write_text("## 접수\n이전 안내입니다.", encoding="utf8")
        self.store.sync(self.folder)

    def topic(self):
        return next(x for x in self.store.view()["topics"] if x["name"]=="접수")

    def adopt(self, unit):
        t = self.topic()
        item = next(x for x in t["candidates"] if x["path"]=="notice.md")
        self.store.decide(t["name"],t["generation"],item["id"],"운영팀","공식 신청 안내",unit)
        return item

    def edit(self, body):
        self.notice.write_text(body,encoding="utf8")
        self.store.sync(self.folder)
        return self.topic()

    def test_only_selected_sentence_or_its_resolved_link_reopens(self):
        t = self.topic()
        selected = self.adopt(1)
        other = self.original.replace("방문 접수합니다.","방문은 오전에 접수합니다.").replace("/unrelated","/new")
        (self.folder/"guide.md").write_text("## 접수\n새 참고 안내",encoding="utf8")
        self.assertEqual(self.edit("\n"+other)["status"],"adopted")
        updated = self.edit(other.replace("/v1","/v2"))
        self.assertEqual(updated["status"], "review_again")
        old, new = (updated["comparison"][k] for k in ("before","after"))
        self.assertEqual(old["quote"],new["quote"])
        self.assertEqual(old["links"]["form"],"https://example.org/v1")
        self.assertEqual(new["links"]["form"],"https://example.org/v2")
        self.assertEqual(old["version"],selected["version"])
        with self.assertRaises(Conflict):
            self.store.decide(t["name"],t["generation"],selected["id"],"팀","지연")
        self.assertEqual(self.edit(self.original)["status"],"adopted")

    def test_edit_delete_and_readopt(self):
        self.adopt(0)
        t = self.edit(self.original.replace("방문 접수합니다.","우편 접수합니다."))
        self.assertEqual(t["comparison"]["after"]["quote"],"우편 접수합니다.")
        self.adopt(0)
        self.assertIsNone(self.topic()["comparison"])
        t = self.edit(self.original.replace("방문 접수합니다. ",""))
        self.assertEqual(t["comparison"]["before"]["quote"],"우편 접수합니다.")
        self.assertIsNone(t["comparison"]["after"])
        self.assertEqual(len(self.store.view()["decisions"]),2)

    def test_reference_style_and_inline_links(self):
        for markup in ("[form][]","[form]"):
            with self.subTest(markup=markup):
                self.edit(self.original.replace("[신청][form]",markup))
                if self.topic()["status"]=="adopted":
                    self.edit(self.original.replace("/v1","/reset"))
                    self.edit(self.original.replace("[신청][form]",markup))
                self.adopt(1)
                changed = self.edit(self.original.replace("[신청][form]",markup).replace("/v1","/next"))
                self.assertEqual(changed["comparison"]["after"]["links"]["form"],"https://example.org/next")
        inline=self.original.replace("[신청][form]","[신청](https://example.org/apply)")
        self.edit(inline)
        self.adopt(1)
        updated=self.edit(inline.replace("/apply","/new-form"))
        self.assertIn("/new-form", updated["comparison"]["after"]["quote"])

    def test_missing_link_and_ambiguous_duplicate_are_visible(self):
        self.adopt(1)
        updated=self.edit(self.original.replace("[form]: https://example.org/v1",""))
        self.assertEqual(updated["comparison"]["after"]["links"],{})
        updated=self.edit(self.original.replace("[신청][form]을 이용합니다.","[신청][form]을 이용합니다. [신청][form]을 이용합니다."))
        self.assertEqual(updated["comparison"]["reason"],"ambiguous")

    def test_legacy_database_rechecks_even_when_file_hash_is_unchanged(self):
        self.adopt(None)
        self.edit(self.original.replace("/v1","/v2"))
        with self.store.db() as db:
            row=db.execute("SELECT evidence FROM decisions").fetchone()
            evidence=json.loads(row["evidence"])
            for item in evidence:
                del item["references"]
            db.execute("UPDATE decisions SET evidence=?", (json.dumps(evidence),))
            db.execute("UPDATE topics SET status='adopted', comparison=NULL")
            db.execute("PRAGMA user_version=0")
        self.store=Store(self.state)
        self.store.sync(self.folder)
        t=self.topic()
        self.assertEqual(t["status"],"review_again")
        self.assertEqual(t["comparison"]["before"]["links"]["form"],"https://example.org/v1")

    def test_invalid_scope_cannot_create_partial_decision(self):
        with self.assertRaises(ValueError):
            self.adopt(1000)
        self.assertFalse(self.store.view()["decisions"])

