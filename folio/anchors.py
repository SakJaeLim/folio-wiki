"""Locate a saved excerpt in a new edition without treating file hashes as decisions."""

import itertools
import re
from difflib import SequenceMatcher

from .qualifiers import following_qualifiers

# Same-file Markdown references: explicit, collapsed and shortcut forms.
DEFINITION = re.compile(
    r"^ {0,3}\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]+)>|(\S+))", re.MULTILINE
)
REFERENCE = re.compile(r"(?<![\\!])\[([^\]\n]+)\](?:[ \t]*\[([^\]\n]*)\])?")
BREAK = re.compile(
    r"\n[ \t]*\n+|\n(?= {0,3}(?:[-*+] |\d+[.)] |\||\[.+?\]:))|(?<=[!?。！？])\s+|(?<=[^\d]\.)\s+"
)


def normalized(text):
    return " ".join(text.split())


def definitions(body):
    found = {}
    fence = None
    lines = body.splitlines()
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(\x60{3,}|~{3,})", line)
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
        # Markdown permits a reference destination on the following line.
        if line.rstrip().endswith("]:") and index + 1 < len(lines):
            line += " " + lines[index + 1].lstrip()
        if match := DEFINITION.match(line):
            found.setdefault(normalized(match[1]).casefold(), match[2] or match[3])
    return found


def links(text, defs):
    # Inline destinations are already part of the saved literal.
    text = re.sub(
        r"\x60+[^\x60\n]*\x60+|\[[^\]\n]+\]\([^\n]*?\)|^ {0,3}\[[^\]\n]+\]:[^\n]*",
        "",
        text,
        flags=re.MULTILINE,
    )
    result = {}
    for m in REFERENCE.finditer(text):
        key = normalized(m[2] or m[1]).casefold()
        if key in defs:
            result[key] = defs[key]
    return result


def units(item):
    text = item["quote"]
    bounds = [0, *(m.end() for m in BREAK.finditer(text)), len(text)]
    result = []
    line = item["start"]
    for start, end in itertools.pairwise(bounds):
        raw = text[start:end]
        clipped = raw.strip()
        if clipped:
            first = line + raw[: len(raw) - len(raw.lstrip())].count("\n")
            result.append(
                {"quote": clipped, "start": first, "end": first + clipped.count("\n")}
            )
        line += raw.count("\n")
    return result


def excerpt(item, unit=None):
    part = item if unit is None else unit
    return {
        "path": item["path"],
        "version": item["version"],
        "quote": part["quote"],
        "start": part["start"],
        "end": part["end"],
        "links": links(part["quote"], item["references"]),
    }


def locate(old, current, index):
    prev = [normalized(u["quote"]) for u in units(old)]
    now = units(current)
    texts = [normalized(u["quote"]) for u in now]
    needle = prev[index]
    matches = [i for i, t in enumerate(texts) if t == needle]
    if len(matches) == prev.count(needle) == 1:
        return now[matches[0]], None
    if matches and len(matches) != prev.count(needle):
        return None, "ambiguous"
    for tag, i, j, k, l in SequenceMatcher(
        None, prev, texts, autojunk=False
    ).get_opcodes():
        if i <= index < j:
            if tag == "equal":
                return now[k + index - i], None
            if k == l:
                return None, "removed"
            first, last = now[k], now[l - 1]
            if j - i == l - k:
                return now[k + index - i], None
            return {
                "quote": "\n".join(u["quote"] for u in now[k:l]),
                "start": first["start"],
                "end": last["end"],
            }, "alignment"
    return None, "removed"


def comparison(chosen, items):
    index = chosen.get("unit")
    old = excerpt(chosen, units(chosen)[index] if index is not None else None)
    same = [item for item in items if item["path"] == chosen["path"]]
    current, reason = None, None
    if len(same) == 1:
        item = same[0]
        part = item
        if index is not None:
            part, reason = locate(chosen, item, index)
        if part:
            current = excerpt(item, part)
    else:
        reason = "ambiguous" if same else "removed"
    if (
        reason is None
        and normalized(old["quote"]) == normalized(current["quote"])
        and old["links"] == current["links"]
    ):
        if index is not None:
            changes = exception_changes(chosen, item, index, part)
            if changes:
                return {
                    "before": old,
                    "after": current,
                    "reason": "exception",
                    "exceptions": changes,
                }
        return None
    return {"before": old, "after": current, "reason": reason or "changed"}


def exception_changes(chosen, current, index, matched):
    """Compare applicable clauses against the edition the reviewer actually adopted."""
    original_parts, current_parts = units(chosen), units(current)
    current_index = current_parts.index(matched)

    def evidence(item, parts, at):
        found = {}
        for clause in following_qualifiers(item, parts, at):
            source = excerpt(item, clause)
            key = (normalized(source["quote"]), tuple(sorted(source["links"].items())))
            found[key] = source
        return found

    old = evidence(chosen, original_parts, index)
    new = evidence(current, current_parts, current_index)
    if old.keys() == new.keys():
        return None

    def present(item, parts):
        return {
            (
                normalized(p["quote"]),
                tuple(sorted(links(p["quote"], item["references"]).items())),
            )
            for p in parts
        }

    # Inserting an unrelated paragraph can move an unchanged exception across
    # a block boundary. Do not report its text as added or removed in that case.
    formerly_present = present(chosen, original_parts)
    now_present = present(current, current_parts)
    removed = [v for k, v in old.items() if k not in now_present]
    added = [v for k, v in new.items() if k not in formerly_present]
    if removed or added:
        return {"removed": removed, "added": added}
