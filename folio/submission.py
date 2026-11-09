"""Bind explicit HWP timing clauses to the documents they actually name."""

import re
from collections import defaultdict

from .hwp_notice import flat

PHASE = re.compile(
    r"서류\s*평가\s*(?:통과|합격)(?:자(?:에\s*한하여|에\s*한해|를\s*대상으로)?|\s*(?:이후|후))|(?:사업\s*)?신청\s*(?:시점|시|할\s*때)|접수\s*시"
)
QUOTED = re.compile(r"[‘“'\"]([^‘’“”'\"]{1,90})[’”'\"]")
ALTERNATE = re.compile(r"대체|갈음|대신")
WINDOW = re.compile(
    r"(?:\d{2,4}[./년]\s*\d{1,2}[./월]\s*\d{1,2}(?:일)?|\d{1,2}월\s*\d{1,2}일|"
    r"\d+(?:\s*영업)?\s*(?:일|시간|주|개월)|당일|익일|다음\s*날|마감일)"
    r"(?:\s*(?:까지|이내|이전|이후|전|후))?|(?:주관기관|기관)의?\s*(?:별도\s*)?안내에\s*따라"
)
# The notice uses broader names in its introductory paragraph than in its table.
CATEGORY = {
    "공통서류": "신청자격증빙서류",
    "기타참고자료": "기타증빙서류",
    "가점관련증빙서류": "가점증빙서류",
}


def compact(text):
    return re.sub(r"[\s()·]", "", text)


def phase(text):
    values = {
        "after" if m[0].startswith("서류") else "application"
        for m in PHASE.finditer(text)
    }
    if len(values) == 1 and not re.search(
        r"제출하지|제출할\s*필요가\s*없|제출\s*(?:불필요|불가)|통과\s*전", text
    ):
        return values.pop()
    return "uncertain"


def timing_claim(subject, quote, location):
    # Names sharing a predicate are not part of each other's deadline.
    predicate = QUOTED.sub("", quote)
    return {
        "subject": subject,
        "stage": phase(predicate),
        "location": location,
        "quote": quote,
        "window": [m[0] for m in WINDOW.finditer(predicate)],
    }


def timing_clauses(parts):
    claims = []
    for location, text in parts:
        if not location.startswith("HWP 문단"):
            continue
        # Separate coordinated submission predicates; commas between document
        # names belong to the same list and must never delimit a clause.
        for value in re.split(
            r"(?<=제출하고)[,\s]+|(?<=제출하며)[,\s]+|;|(?<=다\.)\s+", flat(text)
        ):
            quote = flat(value).strip(" ※,")
            if not PHASE.search(quote) or "제출" not in quote:
                continue
            for subject in QUOTED.findall(quote):
                claims.append(timing_claim(subject, quote, location))
    return claims


def refers_to(subject, row):
    name = compact(subject)
    group = compact(row["category"])
    if CATEGORY.get(name, name) == group or name == group + "증빙서류":
        return True
    # Prefer the document name in the overview. Other groups may cite the same
    # word in a note, an example or the name of a substitute.
    heads = [row["text"].splitlines()[0].split("[붙임")[0], row.get("form_title", "")]
    for head in heads:
        head = re.sub(r"^\s*\((?:필수|해당\s*시)\)\s*", "", head)
        head = re.sub(r"\(?신청자\s*명의\)?", "", head)
        doc = re.sub(r"(?:사본|원본|\d+부)+$", "", compact(head))
        if len(name) >= 3 and (name == compact(head) or name == doc):
            return True
    return False


def followup_passage(parts):
    hits = []
    for location, txt in parts:
        lines = [l.strip() for l in txt.splitlines()]
        for i, line in enumerate(lines):
            if re.match(r"^[-◦•]\s*서류평가\s*통과자", line):
                end = i + 1
                while (
                    end < len(lines)
                    and lines[end]
                    and not re.match(r"^[-◦•□<①-⑳]", lines[end])
                ):
                    end += 1
                quote = "\n".join(lines[i:end])
                if "증빙서류" in compact(quote) and "확인" in quote and "제출" in quote:
                    hits.append((location, quote))
    return hits[0] if len(hits) == 1 else None


def application_forms(parts):
    forms = []
    for location, txt in parts:
        header = re.search(r"(?m)^제출서류\s+제출\s*방법[^\n]*$", txt)
        if header:
            for line in txt[header.end() :].strip().splitlines():
                if re.match(r"^[①-⑳].*증빙서류", line):
                    break
                m = re.match(
                    r"^[①-⑳]\s*(사업신청서|사업계획서)\s+(온라인\s*입력|파일\s*첨부)",
                    line,
                )
                if m:
                    forms.append(
                        {
                            "document": m[1],
                            "method": m[2],
                            "location": location,
                            "quote": line,
                        }
                    )
    return forms


def assign(rows, parts):
    """Annotate individual rows; retain separately named post-screening records."""
    claims = timing_clauses(parts)
    by_subject = defaultdict(list)
    for claim in claims:
        matched = [row for row in rows if refers_to(claim["subject"], row)]
        for row in matched:
            row.setdefault("timing", []).append(claim)
        if not matched:
            by_subject[claim["subject"]].append(claim)
    for row in rows:
        # Explicit row text can supplement or contradict a group-level instruction.
        for line in row["text"].splitlines():
            if PHASE.search(line) and "제출" in line:
                row.setdefault("timing", []).append(
                    timing_claim(row["category"], flat(line), row["location"])
                )
    return by_subject


def stage(claims):
    phases = {c["stage"] for c in claims}
    if len(phases) == 1:
        return next(iter(phases))
    return "uncertain"


def valid_conditions(c):
    if not isinstance(c, dict) or c.get("stage") not in (
        "after",
        "application",
        "uncertain",
    ):
        return False
    for field in ("timing", "alternatives"):
        rows = c.get(field)
        if not isinstance(rows, list):
            return False
        for r in rows:
            if not isinstance(r, dict) or not all(
                isinstance(r.get(k), str) for k in ("location", "quote")
            ):
                return False
            if field == "timing" and (
                r.get("stage") not in ("after", "application", "uncertain")
                or not isinstance(r.get("window", []), list)
                or not all(isinstance(w, str) for w in r.get("window", []))
            ):
                return False
    return True


def conditions(row):
    claims = row.get("timing", [])
    alternatives = [
        {"location": row["location"], "quote": flat(line)}
        for line in row["text"].splitlines()
        if ALTERNATE.search(line)
    ]
    alternatives.extend(row.get("form_alternatives", []))
    return {"stage": stage(claims), "timing": claims, "alternatives": alternatives}


def schedule(sources, named, targets):
    owners = {
        (path, loc): topic
        for topic, members in targets.items()
        for path, locations in members.items()
        for loc in locations
    }
    entries = []
    for path, rows in sources.items():
        for row in rows + named.get(path, []):
            primary = row["text"].split("[붙임")[0]
            heading = (
                flat(primary)
                if row["category"].startswith("기타")
                else primary.splitlines()[0].strip()
            )
            heading = row.get("form_title", heading)
            if (detail := row.get("detail")) and "]" in detail:
                heading = detail.split("]", 1)[1].split(" *")[0].strip(" -")
            entries.append(
                {
                    "path": path,
                    "location": row["location"],
                    "document": heading,
                    "category": row["category"],
                    "topic": owners.get((path, row["location"])),
                    **conditions(row),
                }
            )
    return entries
