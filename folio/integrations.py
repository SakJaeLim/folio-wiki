import asyncio
import functools
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


@functools.lru_cache(maxsize=24)
def outline(path, version, body, directory):
    """Index the stored version, including when the original folder changes."""
    try:
        from pageindex.page_index_md import md_to_tree
    except ImportError:
        return {"provider": "unavailable", "nodes": []}
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        source = Path(tmp) / "source.md"
        source.write_bytes(body.encode("utf-8"))
        try:
            tree = asyncio.run(
                md_to_tree(
                    str(source),
                    if_thinning=False,
                    if_add_node_summary="no",
                    if_add_doc_description="no",
                    if_add_node_text="yes",
                    if_add_node_id="yes",
                )
            )
        except (OSError, ValueError, KeyError, RuntimeError):
            return {"provider": "unavailable", "nodes": []}
    lines = body.splitlines()
    nodes = []

    def walk(items):
        for item in items:
            n = item.get("line_num", 0)
            if 1 <= n <= len(lines) and item["title"].strip() in lines[n - 1]:
                nodes.append({"title": item["title"], "line": n})
            walk(item.get("nodes", []))

    walk(tree["structure"])
    return {"provider": "PageIndex", "nodes": nodes}


def advice(items):
    if len(items) != 2:
        raise ValueError("두 원문을 선택해 주세요.")
    exe = shutil.which("jev")
    if not exe:
        raise ValueError("jev-cli를 설치하고 공식 제공자 인증을 설정해 주세요.")
    spec = json.loads(
        Path(__file__).with_name("decision-question.json").read_text(encoding="utf8")
    )
    payload = {
        "model": spec["model"],
        "state": {"document_a": items[0]["quote"], "document_b": items[1]["quote"]},
        "questions": {"relation": spec["question"]},
    }
    cmd = [exe, "run", "--provider", "official", "-"]
    try:
        run = subprocess.run(
            cmd,
            check=False,
            input=json.dumps(payload).encode("utf8"),
            capture_output=True,
            timeout=45,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Jev 응답 시간이 초과됐습니다.") from exc
    if run.returncode:
        raise ValueError(
            f"Jev 호출 실패 ({run.returncode}). 결정을 저장하지 않았습니다."
        )
    data = json.loads(run.stdout)
    result = data["answers"]["relation"]
    keys = set(spec["question"]["criteria"])
    probs = result["probabilities"]
    if (
        data.get("model") != spec["model"]
        or result.get("type") != "choice"
        or result["choice"] not in keys
        or set(probs) != keys
        or not all(
            isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1
            for v in probs.values()
        )
        or not math.isclose(sum(probs.values()), 1, abs_tol=0.03)
    ):
        raise ValueError("Jev 응답 형식을 확인할 수 없습니다.")
    return {"model": data["model"], "choice": result["choice"], "probabilities": probs}
