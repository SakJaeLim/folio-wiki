"""Read HWP 5 tables with kordoc, keeping checklist cells and explicit spans."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def convert(raw):
    if not raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise ValueError("HWP 5 형식의 파일이 아닙니다.")
    executable = shutil.which("kordoc")
    node = shutil.which("node")
    if not executable or not node:
        raise ValueError("HWP를 읽으려면 Node.js와 kordoc를 설치해 주세요.")
    cli = Path(executable).resolve()
    if os.name == "nt":
        cli = cli.parent / "node_modules/kordoc/dist/cli.js"
    if not cli.is_file():
        raise ValueError("설치한 kordoc CLI의 경로를 확인해 주세요.")
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "source.hwp").write_bytes(raw)
        out = directory / "source.json"
        try:
            subprocess.run(
                [
                    node,
                    "--max-old-space-size=256",
                    str(cli),
                    "source.hwp",
                    "--format",
                    "json",
                    "-o",
                    "source.json",
                ],
                cwd=tmp,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=30,
            )
            if not out.is_file() or out.stat().st_size > 12 << 20:
                raise ValueError("HWP 추출 결과가 없거나 용량 한도를 넘었습니다.")
            data = json.loads(out.read_bytes())
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            raise ValueError(
                "HWP 원문을 읽을 수 없습니다. 파일 형식과 kordoc 설치를 확인해 주세요."
            ) from None
    if (
        not data.get("success")
        or data.get("fileType") != "hwp"
        or not data.get("blocks")
    ):
        raise ValueError("읽을 수 있는 HWP 본문이 없습니다.")
    return data["blocks"]


def flat(text):
    return " ".join(text.split())


def leaf_cells(cells):
    for row in cells:
        for cell in row:
            nested = [
                b["table"]["cells"]
                for b in cell.get("blocks", [])
                if b.get("type") == "table"
            ]
            if nested:
                for children in nested:
                    yield from leaf_cells(children)
            else:
                yield cell["text"]


def read_blocks(blocks):
    parts, rows, details = [], [], {}
    ref = None
    for block in blocks:
        if block["type"] != "table":
            value = block.get("text", "").strip()
            if value:
                parts.append((f"HWP 문단 {len(parts) + 1}", value))
                marker = re.fullmatch(r"\[붙임\s*(\d+)\]", value)
                ref = marker[1] if marker else None
            continue
        table = block["table"]
        cells = table["cells"]
        if not cells:
            continue
        label = "HWP 표 " + table["sourceId"]
        lines = ["　".join(c["text"] for c in row if c.get("text")) for row in cells]
        parts.append((label, "\n".join(lines)))
        if ref:
            # Only the explicitly numbered form may expand its checklist row.
            details.setdefault(ref, []).append((label, cells))
            ref = None
        headers = [re.sub(r"\s", "", c["text"]) for c in cells[0]]
        if not {"구분", "제출서류"}.issubset(headers):
            continue
        group_col, first = headers.index("구분"), headers.index("제출서류")
        last = first + cells[0][first].get("colSpan", 1)
        category, until = "", 0
        for i, row in enumerate(cells[1:], 2):
            if len(row) < last or group_col >= len(row):
                continue
            cell = row[group_col]
            if cell["text"].strip():
                category = flat(cell["text"])
                until = i + cell.get("rowSpan", 1) - 1
            if i > until:
                category = ""
            content = [
                c["text"].strip()
                for c in row[first:last]
                if c["text"].strip() and not re.fullmatch(r"[①-⑳]", c["text"].strip())
            ]
            if category and content:
                rows.append(
                    {
                        "category": category,
                        "text": "\n".join(content),
                        "location": f"{label} {i}행",
                    }
                )
    for row in rows:
        match = re.search(r"\[붙임\s*(\d+)\]", row["text"])
        forms = details.get(match[1], []) if match else []
        if len(forms) != 1:
            continue
        label, cells = forms[0]
        # The exact document name (e.g. a diploma certificate) may appear only
        # in the form referenced from the overview. Keep its explicit locator.
        snippets = []
        for value in leaf_cells(cells):
            extra = re.search(r"※\s*제출서류\s*\n((?:\s*-\s*[^\n]+\n?)+)", value)
            if extra:
                snippets.append(extra[1].strip())
                snippets.extend(
                    line.strip()
                    for line in value.splitlines()
                    if line.lstrip().startswith("*")
                )
        if snippets:
            row["detail"] = f"[붙임 {match[1]} · {label}] " + " ".join(snippets)
    if not parts:
        raise ValueError("HWP에서 확인할 문단이나 표가 없습니다.")
    return parts, rows
