"""Link a checklist row only inside a compatible section of the same notice."""

import re
from collections import defaultdict
from dataclasses import dataclass

from .hwp_notice import flat


def compact(value):
    return re.sub(r"[^가-힣a-z0-9]", "", value.lower())


@dataclass(frozen=True)
class Passage:
    page: str
    group: str
    text: str
    number: str = ""

    @property
    def lead(self):
        return self.text.split("\n")[0]


def numbered(lines, page):
    group = ""
    row = []
    for line in [*lines, ""]:
        header = re.match(r"^번호\s+(.+제출서류.*?)\s+비고$", line)
        n = re.match(r"^(\d{1,2})(?:\s+|$)", line)
        if row and (header or n or not line):
            yield Passage(page, group, "\n".join(row), row[0].split()[0])
            row = []
        if header:
            group = header[1]
        elif group and n:
            row = [line]
        elif row and line:
            # A global validity note belongs to the table, not the last record.
            if line.startswith(("※ 모든 서류", "□", "■")):
                yield Passage(page, group, "\n".join(row), row[0].split()[0])
                row, group = [], ""
            else:
                row.append(line)


def policy(parts):
    out = []
    for page, text in parts:
        lines = [s.strip() for s in text.splitlines() if s.strip()]
        out.extend(numbered(lines, page))
        group = ""
        for i, line in enumerate(lines):
            joined = compact(line)
            if line.startswith("□"):
                group = "예외" if re.search(r"자격\s*예외|예외\s*요건", line) else ""
            if joined == "가점":
                group = "가점"
            if joined == "서류평가면제" or (
                joined == "면제" and i and compact(lines[i - 1]) == "서류평가"
            ):
                group = "면제"
            if joined in ("우선", "우선선정"):
                group = ""
            if re.match(r"^[①-⑳]\s*증빙서류\s*[(（]", line) and "필수" in line:
                out.append(Passage(page, "필수 증빙", line))
            if not group:
                continue
            bullet = r"[①-⑳]" if group == "예외" else r"[⦁•]"
            if not re.match(bullet, line):
                continue
            body = [line]
            for following in lines[i + 1 :]:
                if re.match(r"[①-⑳⦁•□]", following) or compact(following) in {
                    "우선",
                    "우선선정",
                    "서류평가",
                    "면제",
                    "가점",
                }:
                    break
                body.append(following)
            out.append(Passage(page, group, "\n".join(body)))
    return out


def select(row, passages):
    category, text = row["category"], row["text"]
    # A numbered application checklist must match the document name AND the
    # row number in a submission table. A number alone is not an identity.
    if category.isdecimal():
        name = re.sub(r"^[•○\s]+", "", text.split("(")[0]).strip()
        norm = compact(name)
        # '등록증' and '등록증명서' are different documents even on the same row.
        pattern = r"^" + r"[\W_]*".join(map(re.escape, norm)) + r"(?=$|[\W_])"
        hits = [
            p
            for p in passages
            if p.number == category
            and len(norm) >= 3
            and re.search(pattern, re.sub(r"^\d+\s*", "", p.text).lower())
        ]
        return hits, name
    subject = re.sub(r"^\([^)]*\)\s*", "", flat(text.split("[붙임")[0])).strip()
    if "가점" in category or "면제" in category:
        group = "가점" if "가점" in category else "면제"
        subject = re.split(r"\s*(?:증빙|통과\s*증빙)", subject)[0]
        # Match the specific subject in the leading condition (including its
        # wrapped continuation), never in lists of examples beneath it.
        words = [
            w
            for w in re.findall(r"[가-힣]{2,}", subject)
            if w
            not in {
                "해당",
                "최근",
                "이내",
                "정부",
                "주관",
                "이상",
                "전국",
                "규모",
                "훈격",
            }
        ]
        hits = []
        for p in passages:
            lead = re.split(r"\n[-*※\[]", p.text, maxsplit=1)[0]
            numbers = re.findall(r"\d+(?:\.\d+)*", subject)
            source_numbers = re.findall(r"\d+(?:\.\d+)*", lead)
            if (
                p.group == group
                and len(set(words)) >= 2
                and all(w in compact(lead) for w in words)
                and all(n in source_numbers for n in numbers)
                and not re.search(r"제외|불인정|인정하지", lead)
            ):
                hits.append(p)
        return hits, subject
    if "신청자격" in category and "(필수)" in text:
        return [p for p in passages if p.group == "필수 증빙"], category
    subject = re.sub(r"(?:보유자|해당자|대상자)$", "", compact(category))
    if len(subject) >= 3 and "증빙" not in subject:
        return [
            p for p in passages if p.group == "예외" and subject in compact(p.lead)
        ], category
    return [], category


def proof_links(parts, sources):
    passages = policy(parts)
    rules, targets, unresolved = {}, defaultdict(lambda: defaultdict(list)), []
    for path, rows in sources.items():
        for row in rows:
            hits, subject = select(row, passages)
            if len(hits) != 1:
                unresolved.append(
                    {
                        "path": path,
                        **row,
                        "reason": "본문에 대응하는 요건이 여러 개임"
                        if hits
                        else "본문의 대응 요건을 확인하지 못함",
                    }
                )
                continue
            p = hits[0]
            title = f"{p.group} · {subject}"
            quote = p.text
            if p.number:
                # Preserve the section header that distinguishes mandatory from optional.
                quote = f"{p.group}\n{quote}"
            if title in rules and rules[title] != (p.page, quote):
                raise ValueError("증빙 기준의 제목과 원문 위치가 중복됩니다.")
            rules[title] = p.page, quote
            targets[title][path].append(row["location"])
    return rules, dict(targets), unresolved


def proof_markdown(rows):
    return "\n".join(
        f"## {row['location']}\n"
        + flat(row["category"])
        + "\n"
        + row["text"].strip()
        + ("\n" + row["detail"] if row.get("detail") else "")
        + "\n"
        for row in rows
    )
