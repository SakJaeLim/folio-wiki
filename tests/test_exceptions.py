import tempfile
import unittest
from pathlib import Path

from folio.anchors import comparison
from folio.store import Store


class EligibilityContext(unittest.TestCase):
    def test_same_action_must_apply_to_the_selected_audience(self):
        text = "Eligibility for applications:\n\n* At least five credits are required for [Program Members]."
        old = {
            "path": "guide.md",
            "version": "old",
            "topic": "Eligibility",
            "start": 1,
            "end": 3,
            "quote": text,
            "references": {},
            "unit": 1,
        }
        for clause, expected in (
            ("All [Program Members] are eligible to apply.", True),
            ("All [Program Members] may download an application checklist.", False),
            ("All photography club members are eligible to apply.", False),
        ):
            with self.subTest(clause=clause):
                current = dict(old, version="new", quote=text + "\n  " + clause, end=4)
                # Keep the added sentence distinct from the selected one.
                result = comparison(old, [current])
                self.assertEqual(result is not None, expected)
                if expected:
                    self.assertEqual(result["exceptions"]["added"][0]["start"], 4)


class ExceptionReview(unittest.TestCase):
    rule = "회원은 기여 50회 이상이어야 투표할 수 있습니다."
    exception = "다만 신규 회원은 기여 횟수와 관계없이 투표할 수 있습니다."

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.folder = self.root / "source"
        self.folder.mkdir()
        self.file = self.folder / "notice.md"
        (self.folder / "notes.md").write_text(
            "## 투표 자격\n회원 기준을 확인합니다.", encoding="utf8"
        )
        self.store = Store(self.root / "state")
        self.base = "## 투표 자격\n" + self.rule + "\n"
        self.sync(self.base)
        self.adopt()

    def view(self):
        return self.store.view()["topics"][0]

    def sync(self, text):
        self.file.write_text(text, encoding="utf8")
        self.store.sync(self.folder)
        return self.view()

    def adopt(self):
        topic = self.view()
        chosen = next(c for c in topic["candidates"] if c["path"] == self.file.name)
        index = next(
            i for i, u in enumerate(chosen["units"]) if u["quote"] == self.rule
        )
        self.store.decide(
            topic["name"],
            topic["generation"],
            chosen["id"],
            "운영팀",
            "투표 기준 확인",
            index,
        )

    def test_exception_and_archived_source_then_readopt_and_remove(self):
        new = self.base + "\n" + self.exception + "\n"
        t = self.sync(new)
        c = t["comparison"]
        self.assertEqual(t["status"], "review_again")
        self.assertEqual(c["reason"], "exception")
        self.assertEqual(c["before"]["quote"], c["after"]["quote"])
        added = c["exceptions"]["added"][0]
        lines = self.store.source(added["path"], added["version"])["body"].splitlines()
        self.assertEqual(lines[added["start"] - 1 : added["end"]], [self.exception])
        self.assertEqual(self.sync(new)["generation"], t["generation"])
        self.adopt()
        self.assertEqual(self.sync(new)["status"], "adopted")
        change = self.sync(self.base)["comparison"]
        self.assertEqual(
            [x["quote"] for x in change["exceptions"]["removed"]], [self.exception]
        )
        self.assertEqual(change["exceptions"]["added"], [])
        self.assertEqual(self.sync(new)["status"], "adopted")

    def test_unrelated_and_other_rules(self):
        for addition in (
            "투표 회의록은 다음 주에 공개합니다.",
            "다만 모든 회원은 투표 안내서를 내려받을 수 있습니다.",
            "다만 신규 회원은 주차를 신청할 수 있습니다.",
            "\n## 신청 자격\n" + self.exception,
            "\n* 장학금 지원 기준입니다.\n  " + self.exception,
        ):
            with self.subTest(addition=addition):
                self.assertEqual(self.sync(self.base + addition)["status"], "adopted")

    def test_unchanged_accepted_exception_survives_unrelated_insert(self):
        new = self.base + self.exception + "\n"
        self.sync(new)
        self.adopt()
        modified = self.base + "\n주차장은 본관 옆에 있습니다.\n\n" + self.exception
        self.assertEqual(self.sync(modified)["status"], "adopted")

    def test_note_between_anchor_and_pending_exception_does_not_clear_it(self):
        self.sync(self.base + self.exception)
        t = self.sync(self.base + "\n주차장은 본관 옆에 있습니다.\n\n" + self.exception)
        self.assertEqual(t["status"], "review_again")
        self.assertEqual(t["comparison"]["exceptions"]["added"][0]["start"], 6)

    def test_existing_v1_snapshot_reassessed_without_new_edit(self):
        t = self.sync(self.base + self.exception)
        with self.store.db() as db:
            db.execute("UPDATE topics SET status='adopted',comparison=NULL")
            db.execute("PRAGMA user_version=1")
        self.store = Store(self.root / "state")
        self.store.sync(self.folder)
        self.assertEqual(self.view()["comparison"], t["comparison"])
        self.assertEqual(len(self.store.view()["decisions"]), 1)

    def test_exception_edit_preserves_both_versions(self):
        new = self.base + self.exception
        self.sync(new)
        self.adopt()
        changed = self.sync(new.replace("신규 회원", "명예 회원"))["comparison"]
        self.assertEqual(changed["exceptions"]["removed"][0]["quote"], self.exception)
        self.assertIn("명예 회원", changed["exceptions"]["added"][0]["quote"])
