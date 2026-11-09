import unittest

from folio import submission


class SubmissionTest(unittest.TestCase):
    def test_scope_conflict_and_timing_modifiers(self):
        rows = [
            {"category": "1", "text": "재학확인서", "location": "HWP 표 t1 2행"},
            {"category": "2", "text": "졸업확인서", "location": "HWP 표 t1 3행"},
            {
                "category": "면제 증빙서류",
                "text": "추천서",
                "location": "HWP 표 t1 4행",
            },
        ]
        claim = [
            (
                "HWP 문단 2",
                "‘재학확인서’는 신청 시 제출하고, 서류평가 통과 후 3일 이내에 ‘졸업확인서’를 제출",
            ),
            ("HWP 문단 3", "‘재학확인서’는 서류평가 통과 후 제출"),
        ]
        remaining = submission.assign(rows, claim)
        self.assertFalse(remaining)
        self.assertEqual(submission.conditions(rows[0])["stage"], "uncertain")
        self.assertEqual(submission.conditions(rows[1])["stage"], "after")
        self.assertEqual(rows[1]["timing"][0]["window"], ["3일 이내"])
        self.assertFalse(submission.conditions(rows[2])["timing"])

    def test_does_not_attach_substitute_to_other_subjects(self):
        row = {
            "category": "가점 증빙서류",
            "location": "HWP 표 t1 2행",
            "text": "수상 증명서\n추천서로 대체 가능",
        }
        pending = submission.assign([row], [("HWP 문단 1", "‘추천서’는 신청 시 제출")])
        self.assertFalse(
            submission.refers_to(
                "등록확인서", {"category": "기타", "text": "미등록확인서"}
            )
        )
        self.assertIn("추천서", pending)
        self.assertEqual(submission.conditions(row)["stage"], "uncertain")
