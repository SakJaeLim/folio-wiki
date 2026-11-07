"""A writable copy of the workshop example for first-time reviewers."""

import os
import shutil
import tempfile
from pathlib import Path


def demo_folder(root: Path) -> Path:
    folder = root / ".state" / "demo" / "공개 워크숍"
    if folder.resolve() != folder:
        raise ValueError("데모 폴더 경로에 연결된 다른 디렉터리가 있습니다.")
    return folder


def prepare(root: Path) -> Path:
    folder = demo_folder(root)
    if folder.is_dir():
        return folder
    folder.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=folder.parent) as tmp:
        staged = Path(tmp) / "sample"
        shutil.copytree(root / "examples/public-handbook", staged)
        try:
            staged.rename(folder)
        except OSError:
            if not folder.is_dir():
                raise
    return folder


def revise(root: Path) -> None:
    name = "02-모집공지.md"
    notice = demo_folder(root) / name
    if not notice.is_file() or notice.resolve() != notice:
        raise ValueError("먼저 python run.py --demo 명령으로 예제를 시작해 주세요.")
    replacement = (root / "examples/revision" / name).read_bytes()
    current = notice.read_bytes()
    if current == replacement:
        return
    if current != (root / "examples/public-handbook" / name).read_bytes():
        raise ValueError("직접 수정한 공지입니다. 파일에서 기한을 변경해 주세요.")
    with tempfile.NamedTemporaryFile(dir=notice.parent, delete=False) as tmp:
        tmp.write(replacement)
        staged = Path(tmp.name)
    try:
        os.replace(staged, notice)
    finally:
        staged.unlink(missing_ok=True)
