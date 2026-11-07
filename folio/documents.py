"""Read an explicitly selected public Markdown folder. Locators use original lines."""

import hashlib
import os
import re
import stat
from pathlib import Path


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def public_files(folder):
    root = Path(folder).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("공개 자료 폴더를 찾을 수 없습니다.")
    files = {}

    def fail(exc):
        raise exc

    for base, dirs, names in os.walk(root, followlinks=False, onerror=fail):
        dirs[:] = [
            name
            for name in sorted(dirs)
            if not name.startswith(".") and not _link(Path(base, name))
        ]
        for name in sorted(names):
            path = Path(base, name)
            if (
                name.startswith(".")
                or path.suffix.lower() not in {".md", ".markdown"}
                or _link(path)
            ):
                continue
            if not path.resolve(strict=True).is_relative_to(root) or not path.is_file():
                continue
            if len(files) >= 60 or path.stat().st_size > 512_000:
                raise ValueError(
                    "공개 폴더는 Markdown 60개, 파일당 512 KB까지 지원합니다."
                )
            raw = path.read_bytes()
            body = raw.decode("utf-8")
            relative = path.relative_to(root).as_posix()
            files[relative] = {
                "path": relative,
                "version": hashlib.sha256(raw).hexdigest(),
                "body": body,
            }
    return files


def _link(path):
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def sections(doc):
    lines = doc["body"].removeprefix("\ufeff").splitlines()
    spans, current, fence = [], None, None
    parents = {}
    for i, line in enumerate(lines, 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif (
                token[0] == fence[0]
                and len(token) >= len(fence)
                and not line.strip()[len(token) :].strip()
            ):
                fence = None
            continue
        if fence:
            continue
        match = re.match(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*$", line)
        if not match:
            continue
        if current is not None:
            spans.append((*current, i - 1))
        depth, title = len(match[1]), re.sub(r"\s+#+\s*$", "", match[2]).strip()
        parents = {k: v for k, v in parents.items() if k < depth}
        parents[depth] = title
        topic = " / ".join(parents[k] for k in sorted(parents) if k > 1)
        current = (topic or title, i, depth)
    if current:
        spans.append((*current, len(lines)))
    result = []
    for title, start, depth, end in spans:
        first, last = start + 1, end
        while first <= last and not lines[first - 1].strip():
            first += 1
        while last >= first and not lines[last - 1].strip():
            last -= 1
        if first > last or depth == 1:
            continue
        quote = "\n".join(lines[first - 1 : last])
        item = {
            "topic": title,
            "path": doc["path"],
            "version": doc["version"],
            "start": first,
            "end": last,
            "quote": quote,
        }
        item["id"] = digest(f"{doc['path']}\0{doc['version']}\0{first}:{last}")
        result.append(item)
    return result
