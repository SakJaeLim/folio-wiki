"""Resolve an exception to a rule in a different section of the same edition."""

import re
from urllib.parse import unquote

from .anchors import excerpt, links, locate, normalized, units
from .qualifiers import plain

NUMBER = r"[①-⑳]"
NUMBERED = re.compile(rf"^({NUMBER})\s*(.+)")
CITE = rf"{NUMBER}항\([^()]+\)"
CITE_LIST = rf"{CITE}(?:[,·]?(?:및|와|과)?{CITE})*"
OPERATIVE = re.compile(r"적용\s*(?:예외|제외)|면제")
DEST = re.compile(r"\[[^]\n]+\]\(#([^)\s]+)\)")
SUBJECT = re.compile(r"^(.+?)(?:은|는|의\s*경우)(?=\s|[,，])", re.DOTALL)


def compact(text):
    return re.sub(r"\s+", "", text).casefold()


def slug(title):
    return re.sub(r"[^\w -]", "", title.casefold()).strip().replace(" ", "-")


def paragraphs(item):
    # Keep a wrapped paragraph together. In particular 'Ⅲ.' within a
    # citation is not a sentence ending. Ignore examples and quoted text.
    lines = item["quote"].splitlines()
    fenced = None
    comment = False
    block = []
    start = item["start"]
    for i, line in enumerate([*lines, ""], item["start"]):
        marker = re.match(r"^ {0,3}(\x60{3,}|~{3,})", line)
        hidden = not fenced and (comment or "<!--" in line)
        if hidden:
            comment = "-->" not in line
        boundary = (
            hidden or not line.strip() or re.match(r"^\s*(?:[•*>+-]|\d+\.)\s*", line)
        )
        if marker or fenced or boundary:
            if block:
                yield {"quote": "\n".join(block), "start": start, "end": i - 1}
                block = []
        if hidden:
            continue
        if marker:
            if not fenced:
                fenced = marker[1]
            elif marker[1].startswith(fenced) and line.strip() == marker[1]:
                fenced = None
            continue
        if fenced or not line.strip() or line.lstrip().startswith((">", "<!--")):
            continue
        if not block:
            start = i
        block.append(line)


def rule_reference(selected, sections):
    """Compile references only where the selected rule resolves uniquely."""
    parts = units(selected)
    index = selected.get("unit")
    title = selected["topic"].split(" / ")[-1]
    names = [s["topic"].split(" / ")[-1] for s in sections]
    if names.count(title) != 1:
        return None
    fragment = (
        slug(title)
        if (index is None or len(parts) == 1)
        and sum(slug(n) == slug(title) for n in names) == 1
        else None
    )
    numbers = {}
    if re.match(r"^(?:[Ⅰ-Ⅻ]+|[0-9]+|제\s*\d+\s*장)[.\s]", title):
        candidates = [NUMBERED.match(p["quote"]) for p in parts]
        selected_numbers = candidates if index is None else [candidates[index]]
        for m in selected_numbers:
            if m and sum(1 for c in candidates if c and c[1] == m[1]) == 1:
                numbers[m[1]] = m[2].splitlines()[0]
    pattern = (
        re.compile(
            r"(?<![\dⅠ-Ⅻ])"
            + re.escape(compact(title))
            + f"({CITE_LIST})(?:만)?(?:적용예외|적용제외|면제)"
        )
        if numbers
        else None
    )
    return (fragment, pattern, numbers) if fragment or numbers else None


def cites_rule(text, reference):
    fragment, pattern, titles = reference
    text = re.sub(r"\x60+[^\x60]*\x60+", "", text)
    if not OPERATIVE.search(text) or re.search(
        r"(?:예외|제외|면제)\s*(?:[가이]?\s*아[님니]|없|불가|하지\s*않|되지\s*않|대상이\s*아)",
        text,
    ):
        return False
    if fragment and any(
        unquote(match[1]).casefold() == fragment
        and re.match(
            r"\s*(?:기준\s*)?(?:적용\s*(?:예외|제외)|면제)", text[match.end() :]
        )
        for match in DEST.finditer(text)
    ):
        return True
    if pattern:
        for citation in pattern.finditer(compact(text)):
            for n, label in re.findall(rf"({NUMBER})항\(([^()]+)\)", citation[1]):
                # Require both the numbered address and a matching rule name.
                title = titles.get(n, "")
                name = re.sub(r"\s+(?:기준|요건|제한|대상)$", "", title)
                if name and (
                    compact(title) == label or compact(name.split()[-1]) == label
                ):
                    return True
    return False


def cross_evidence(selected, sections):
    reference = rule_reference(selected, sections)
    if not reference:
        return {}
    scope, audience = selected.get("scope", ""), compact(selected.get("audience", ""))
    found = {}
    for item in sections:
        topic = item["topic"]
        if topic == selected["topic"] or (
            scope and topic != scope and not topic.startswith(scope + " / ")
        ):
            continue
        for p in paragraphs(item):
            text = p["quote"].lstrip(" \t•*-")
            if not cites_rule(text, reference):
                continue
            if audience:
                subject = SUBJECT.match(text)
                if (
                    len(OPERATIVE.findall(text)) != 1
                    or not subject
                    or re.search(r"\S+(?:은|는|의\s*경우)(?=\s)", text[subject.end() :])
                    or audience
                    not in {
                        compact(plain(a))
                        for a in re.split(r"\s*(?:,|·|\s및\s|\s또는\s)\s*", subject[1])
                    }
                ):
                    continue
                # Changes to the OTHER named recipients do not change this
                # recipient's exception. Keep the original quote for display.
                text = text[subject.end() :]
            source = excerpt(item, p)
            source["section"] = topic
            found[
                (
                    topic,
                    normalized(text),
                    tuple(sorted(links(text, item["references"]).items())),
                )
            ] = source
    return found


def with_cross_changes(selected, before, after, change):
    old, new = cross_evidence(selected, before), cross_evidence(selected, after)
    added = [v for k, v in new.items() if k not in old]
    removed = [v for k, v in old.items() if k not in new]
    if not added and not removed:
        return change
    if change is None:
        current = next(s for s in after if s["topic"] == selected["topic"])
        idx = selected.get("unit")
        old_part = units(selected)[idx] if idx is not None else None
        new_part = locate(selected, current, idx)[0] if idx is not None else None
        change = {
            "reason": "exception",
            "before": excerpt(selected, old_part),
            "after": excerpt(current, new_part),
            "exceptions": {"added": [], "removed": []},
        }
    change["exceptions"]["added"].extend(added)
    change["exceptions"]["removed"].extend(removed)
    change["scope"] = selected.get("scope", "")
    change["audience"] = selected.get("audience", "")
    return change
