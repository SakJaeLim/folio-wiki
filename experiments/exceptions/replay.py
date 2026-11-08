"""Replay the official election revision and single-edit controls, without an LLM."""

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from folio.store import Store  # noqa: E402

# File hashes from the pinned Git blobs used in the original ten-question pilot.
FILES = {
    "previous-year": (
        "3aed31a5ca9a52ef8f83c13ac95f82e6d464a9f0",
        2025,
        "8099162e65b50d3f877a7d69437be135bed541d7aca6ed0e4556a62261289701",
    ),
    "session": (
        "e4742ba279006a6b0aa826c7d004a305c920960c",
        2026,
        "2839a281454b970840b0345b4bb72304aa1724710911e8bfd7a7766c81253e91",
    ),
    "final": (
        "3f6c6687d1a005fe5003662b4e6314abcdfb6e2d",
        2026,
        "8bd353854fb9fc0249e80614f10017e53f1ee00b0b2ca471f1ff1f8ba8f477de",
    ),
}
CONTROLS = {
    "meeting-minutes": "Meeting minutes are published on the committee website.",
    "same-audience": "**Eligibility update:** All [Org Members] may download the voting calendar.",
    "different-entitlement": "**Exception:** All [Org Members] are eligible for a parking permit.",
    "already-eligible": "All [Org Members] who are eligible to vote may order refreshments.",
    "different-waiver": "Contributions to the newsletter are exempt from parking fees.",
    "different-voters": "All photography club members may vote for the club president.",
}


def load_sources(corpus):
    data = {}
    for name, (commit, year, digest) in FILES.items():
        uri = f"https://raw.githubusercontent.com/kubernetes/community/{commit}/elections/steering/{year}/README.md"
        if corpus is None:
            with urllib.request.urlopen(uri, timeout=30) as response:
                body = response.read()
        else:
            body = (corpus / (name + ".md")).read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError(f"Unexpected {name} document; check the pinned edition")
        data[name] = body
    return data


def replay(out, data):
    out.mkdir(parents=True, exist_ok=False)
    old_lines = data["session"].splitlines(keepends=True)
    # Insert the synthetic controls on the exact physical line of the official addition.
    assert b"devstats-sql" in old_lines[74] and not old_lines[75].strip()

    def insert(sentence):
        return b"".join(
            old_lines[:75] + [("  " + sentence + "\n").encode()] + old_lines[75:]
        )

    cases = [("official", data["final"], True), ("no-edit", data["session"], False)]
    cases.extend((name, insert(sentence), False) for name, sentence in CONTROLS.items())
    cases.append(
        (
            "paraphrased-grant",
            insert(
                "Regardless of their contribution count, all [Org Members] may vote."
            ),
            True,
        )
    )
    results = []
    for name, body, expect in cases:
        case = out / name
        folder = case / "source"
        folder.mkdir(parents=True)
        (folder / "2025.md").write_bytes(data["previous-year"])
        path = folder / "2026.md"
        path.write_bytes(data["session"])
        store = Store(case / "state")
        store.sync(folder)

        def topic():
            return next(t for t in store.view()["topics"] if t["name"] == "Eligibility")

        t = topic()
        chosen = next(c for c in t["candidates"] if c["path"] == "2026.md")
        index, unit = next(
            (i, p)
            for i, p in enumerate(chosen["units"])
            if "at least 50 contributions" in p["quote"]
        )
        store.decide(
            "Eligibility",
            t["generation"],
            chosen["id"],
            "시험 담당자",
            "2026년 투표 자격",
            index,
        )
        path.write_bytes(body)
        store.sync(folder)
        current = topic()
        change = current["comparison"]
        status = "review_again" if expect else "adopted"
        assert current["status"] == status, (name, current["status"])
        if expect:
            assert (
                change["reason"] == "exception"
                and change["before"]["quote"] == change["after"]["quote"]
            )
            [added] = change["exceptions"]["added"]
            assert added["start"] == added["end"] == 76
            assert added["quote"] == body.decode().splitlines()[75].strip()
            assert added["version"] == hashlib.sha256(body).hexdigest()
        else:
            assert change is None
        results.append(
            dict(
                case=name,
                expected=status,
                observed=current["status"],
                selected_lines=[unit["start"], unit["end"]],
                source_sha256=hashlib.sha256(body).hexdigest(),
                comparison=change,
            )
        )
    (out / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf8"
    )
    for row in results:
        print(row["case"], row["observed"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        help="Optional existing directory with the three pinned Markdown files",
    )
    parser.add_argument("--out", type=Path, help="New directory for cases and results")
    args = parser.parse_args()
    data = load_sources(args.corpus)
    if args.out:
        replay(args.out, data)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            replay(Path(tmp) / "results", data)
