import tempfile
import unittest
from pathlib import Path

from folio.store import Conflict, Store


class ReviewLifecycle(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.folder = self.root / "public"
        self.folder.mkdir()
        self.a = self.folder / "안내.md"
        self.b = self.folder / "공지.md"
        self.a.write_text("# 안내\n## 기한\n7일 전까지 신청합니다.\n", encoding="utf8")
        self.b.write_text("# 공지\n## 기한\n14일 전까지 신청합니다.\n", encoding="utf8")
        self.s = Store(self.root / "state")
        self.s.sync(self.folder)

    def test_adopt_change_delete_restore(self):
        first = self.s.view()["topics"][0]
        choice = next(x for x in first["candidates"] if x["path"] == self.b.name)
        self.s.decide(
            "기한", first["generation"], choice["id"], "담당자", "이번 회차 공지"
        )
        self.s.sync(self.folder)
        self.assertEqual(self.s.view()["topics"][0]["status"], "adopted")
        self.b.write_text("# 공지\n## 기한\n10일 전까지 신청합니다.\n", encoding="utf8")
        self.s.sync(self.folder)
        self.assertEqual(self.s.view()["topics"][0]["status"], "review_again")
        with self.assertRaises(Conflict):
            self.s.decide(
                "기한", first["generation"], choice["id"], "다른 담당자", "늦은 요청"
            )
        self.assertIn("14일", self.s.source(self.b.name, choice["version"])["body"])
        self.b.unlink()
        self.a.unlink()
        self.s.sync(self.folder)
        final = self.s.view()
        self.assertEqual(final["topics"][0]["candidates"], [])
        self.assertEqual(final["decisions"][0]["selection"], choice["id"])
        self.s.decide(
            "기한", final["topics"][0]["generation"], "withdraw", "담당자", "근거 소멸"
        )

    def test_unrelated_source_change_preserves_decision(self):
        t = self.s.view()["topics"][0]
        self.s.decide(
            t["name"], t["generation"], t["candidates"][0]["id"], "담당자", "사유"
        )
        (self.folder / "메모.md").write_text("# 메모\n새 팀원 안내", encoding="utf8")
        self.s.sync(self.folder)
        self.assertEqual(self.s.view()["topics"][0]["status"], "adopted")
        with self.assertRaises(Conflict):
            self.s.decide(
                t["name"],
                t["generation"],
                t["candidates"][1]["id"],
                "다른 담당자",
                "중복",
            )

    def test_unreadable_snapshot_keeps_previous_sources(self):
        before = self.s.view()["snapshot"]
        self.b.write_bytes(b"\xff\xfe")
        with self.assertRaises(UnicodeError):
            self.s.sync(self.folder)
        self.assertEqual(before, self.s.view()["snapshot"])

    def test_hold_can_be_resolved_without_changing_source(self):
        t = self.s.view()["topics"][0]
        self.s.decide(
            t["name"], t["generation"], "hold", "담당자", "적용 대상 확인 필요"
        )
        held = self.s.view()["topics"][0]
        self.assertEqual(held["status"], "held")
        self.s.decide(
            held["name"],
            held["generation"],
            held["candidates"][0]["id"],
            "담당자",
            "범위 확인",
        )
        self.assertEqual(
            [x["selection"] for x in self.s.view()["decisions"]][1], "hold"
        )

    def test_state_directory_is_bound_to_one_folder(self):
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(ValueError):
            self.s.sync(other)
        self.assertEqual(len(self.s.view()["files"]), 2)
