"""Check the association, not just the presence of Korean words in the output."""

import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from folio import hwp_notice
from folio.proof_rules import proof_links


def cell(text, span=1):
    return {"text": text, "rowSpan": span, "colSpan": 1}


def evidence_table(rows):
    return {
        "type": "table",
        "table": {
            "sourceId": "t3",
            "cells": [[cell("구 분"), cell("제출 서류")], *rows],
        },
    }


class HwpProofTest(unittest.TestCase):
    def test_merged_group_stops_at_last_covered_row(self):
        _, rows = hwp_notice.read_blocks(
            [
                evidence_table(
                    [
                        [cell("환경장비 보유자", 2), cell("등록증")],
                        [cell(""), cell("검사증")],
                        [cell(""), cell("잘못된 인계")],
                    ]
                )
            ]
        )
        self.assertEqual([r["category"] for r in rows], ["환경장비 보유자"] * 2)
        self.assertEqual([r["text"] for r in rows], ["등록증", "검사증"])

    def test_ambiguous_or_unrelated_criteria_stay_separate(self):
        row = {
            "category": "가점 증빙서류",
            "location": "표 3행",
            "text": "(해당 시) 최근 2년 연구대회 장관급 수상 증빙",
        }
        wrap = lambda lines: proof_links(
            [("PDF 1쪽", "\n".join(lines))], {"a.md": [row]}
        )[2]
        target = "⦁최근 2년 연구대회 장관급 수상자"
        self.assertFalse(wrap(["가점", target]))
        self.assertTrue(wrap(["서류평가", "면제", target]))
        self.assertTrue(wrap(["가점", target, target]))
        self.assertTrue(wrap(["가점", target.replace("2년", "3년")]))
        self.assertTrue(wrap(["가점", target + " 제외"]))

    def test_number_alone_cannot_connect(self):
        rows = [{"category": "4", "location": "HWP 표 t2 5행", "text": "사업자등록증"}]
        for text in (
            "번호 필수 제출서류 비고\n4 납세증명서",
            "번호 필수 제출서류 비고\n3 사업자등록증",
            "번호 필수 제출서류 비고\n4 사업자등록증명원",
        ):
            self.assertFalse(proof_links([("PDF 1쪽", text)], {"a.md": rows})[0])

    def test_binary_checklist_with_installed_converter(self):
        if not shutil.which("kordoc") and not os.environ.get("CI"):
            self.skipTest("optional HWP converter is not installed")
        # This small synthetic HWP 5 file has two rows, no official/private data.
        raw = (Path(__file__).parent / "fixtures" / "checklist.hwp").read_bytes()
        _, rows = hwp_notice.read_blocks(hwp_notice.convert(raw))
        self.assertEqual(
            rows, [{"category": "1", "text": "등록확인서", "location": "HWP 표 t1 2행"}]
        )

    def test_missing_converter_is_reported(self):
        with (
            patch("folio.hwp_notice.shutil.which", return_value=None),
            self.assertRaisesRegex(ValueError, "kordoc"),
        ):
            hwp_notice.convert(bytes.fromhex("d0cf11e0a1b11ae1"))
