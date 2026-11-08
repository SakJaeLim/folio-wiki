"""Extract a small, inspectable set of rule headings and matching restrictive clauses."""

import re
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from .companions import LIMIT, has_term, restricted
from .hwpx_text import paragraphs

BULLET = re.compile(r"^[•◦▖□○]\s*")
HEADING = re.compile(r"^[가-힣A-Za-z][가-힣A-Za-z0-9 ·ㆍ(),~/-]{0,23}$")
PARTICLE = re.compile(r"(?:으로는|에서는|으로|에서|에게|까지|부터|[을를은는이가의에])$")
STOP = set(
    "신청 지원 가능 불가 제외 면제 사업 비용 집행 사업비 공고 사업화 선정 기준 요건 해당 기간 대상 기업 사업자 창업자 신청자 신청일 사업계획서 사업기간 정부지원사업비 경우 이후 이전 기간 내에 관련 일부 원칙 절차 필요 대한 지급 구매 방법 인정 자금 사용 제출 기관 창업 예비창업자 신청기업 사업수행 등은 다음 따른 참여 또는 일반 자료 확인 모집 포함 제한".split()
)


def pages(raw, name, root=False):
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        if not raw.startswith(b"%PDF"):
            raise ValueError("PDF 원본을 확인할 수 없음")
        try:
            proc = subprocess.run(
                [
                    "pdftotext",
                    "-raw" if root else "-layout",
                    "-enc",
                    "UTF-8",
                    "-f",
                    "1",
                    "-l",
                    "150",
                    "-",
                    "-",
                ],
                input=raw,
                capture_output=True,
                timeout=30,
                check=True,
            )
        except FileNotFoundError:
            raise ValueError(
                "PDF를 읽으려면 pdftotext를 PATH에 설치해 주세요."
            ) from None
        except (subprocess.SubprocessError, OSError):
            raise ValueError("PDF 본문을 추출하지 못했습니다.") from None
        if len(proc.stdout) > 6 << 20:
            raise ValueError("PDF 텍스트 용량 초과")
        parts = proc.stdout.decode("utf8").replace("\r", "").rstrip("\f").split("\f")
        if len(parts) >= 150:
            raise ValueError("PDF 분석 범위(149쪽) 초과")
        # Some imposition exports repeat the entire two-page spread in the
        # text layer of each physical page. Split only at both printed folios.
        if root:
            for i in range(len(parts) - 1):
                if parts[i] != parts[i + 1]:
                    continue
                markers = list(re.finditer(r"(?m)^-\s*(\d+)\s*-$", parts[i]))
                if [int(m[1]) for m in markers] == [i + 1, i + 2]:
                    spread = parts[i]
                    parts[i], parts[i + 1] = (
                        spread[: markers[1].start()],
                        spread[markers[1].start() :],
                    )
        result = [(f"PDF {i}쪽", p) for i, p in enumerate(parts, 1)]
    elif suffix == ".hwpx":
        try:
            with zipfile.ZipFile(BytesIO(raw)) as z:
                members = sorted(
                    (
                        m
                        for m in z.infolist()
                        if re.fullmatch(r"Contents/section\d+\.xml", m.filename)
                    ),
                    key=lambda m: int(re.search(r"\d+", m.filename)[0]),
                )
                if not members or sum(m.file_size for m in members) > 8 << 20:
                    raise ValueError("HWPX 본문 범위를 확인할 수 없음")
                result = []
                for i, m in enumerate(members, 1):
                    xml = z.read(m)
                    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                        raise ValueError("지원하지 않는 HWPX XML 선언")
                    body = ET.fromstring(xml)
                    paras = paragraphs(body)
                    result.append((f"HWPX {i}절", "\n".join(paras)))
        except (zipfile.BadZipFile, ET.ParseError):
            raise ValueError("HWPX 본문을 읽을 수 없음") from None
    else:
        raise ValueError("이 형식은 원문 추출을 지원하지 않습니다.")
    if not any(p.strip() for _, p in result):
        raise ValueError("추출할 텍스트가 없습니다. 스캔 문서는 OCR이 필요합니다.")
    return result


def root_rules(parts):
    """Table row headings preceding bullets and inline labelled policy bullets."""
    rules = {}
    for location, text in parts:
        lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            if not BULLET.match(line):
                continue
            body = BULLET.sub("", line, count=1)
            if re.match(r"^[^:：]{2,26}\s*[:：]", body):
                head = re.split("[:：]", body, maxsplit=1)[0].strip()
            elif (
                i
                and lines[i - 1].startswith("(")
                and lines[i - 1].endswith(")")
                and i >= 2
                and HEADING.fullmatch(lines[i - 2])
            ):
                head = " ".join(lines[i - 2 : i])
            elif i and HEADING.fullmatch(lines[i - 1]):
                head = lines[i - 1]
            else:
                continue
            quote = [body]
            for tail in lines[i + 1 : i + 5]:
                if (
                    BULLET.match(tail)
                    or tail.startswith(("*", "※", "<", "- "))
                    or HEADING.fullmatch(tail)
                    and len(tail.split()) <= 2
                ):
                    break
                quote.append(tail)
                if re.search(r"(?:비용|급여|합니다|한다|있음|없음)[.]?$", tail):
                    break
            entry = (location, " ".join(quote))
            rules.setdefault(head, []).append(entry)
    return {h: rows[0] for h, rows in rules.items() if len(rows) == 1}


def candidate_terms(rules, supplements):
    # Use terms from the operative clause only. A term must label the rule in
    # the notice itself. Unlabelled prose and duplicate headings stay unresolved.
    terms = set()
    for parts in supplements:
        for _, text in parts:
            for line in text.splitlines():
                limit = LIMIT.search(line)
                if not limit:
                    continue
                for tok in re.findall(r"[가-힣]{2,}", line[: limit.start()]):
                    for word in {tok, PARTICLE.sub("", tok)}:
                        if (
                            len(word) >= 2
                            and word not in STOP
                            and restricted(line, [word])
                        ):
                            terms.add(word)
    return {
        head: sorted(t for t in terms if has_term(head, t))
        for head in rules
        if any(has_term(head, t) for t in terms)
    }


def attachment_md(parts):
    def blocks(text):
        answer = []
        for raw in [*text.splitlines(), ""]:
            line = " ".join(raw.split())
            new_answer = line.startswith("☞")
            if answer and (not line or new_answer or re.match(r"^\d+[. ]", line)):
                yield " ".join(answer)
                answer = []
            if not line or line == "답변":
                continue
            if new_answer or answer:
                answer.append(re.sub(r"^답변\s+", "", line))
            else:
                yield line

    return "\n".join(
        "## "
        + label
        + "\n"
        + "\n\n".join(
            " " + block if block.startswith("#") else block for block in blocks(txt)
        )
        for label, txt in parts
    )
