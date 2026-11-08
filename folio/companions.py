"""Local, pinned publication records. Titles and filenames never establish membership."""

import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .anchors import excerpt, locate, normalized, units
from .cross_sections import SUBJECT, cites_rule, compact, paragraphs, rule_reference
from .documents import _link

CATALOG = "folio-sources.json"


def https(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
    )


def read_catalog(folder, docs):
    file = Path(folder) / CATALOG
    if not file.exists() and not file.is_symlink():
        return {}
    if _link(file) or not file.is_file() or file.stat().st_size > 512_000:
        raise ValueError("공고 출처 목록 파일을 확인해 주세요.")
    config = json.loads(file.read_text(encoding="utf-8-sig"))
    if (
        not isinstance(config, dict)
        or config.get("version") != 1
        or not isinstance(config.get("sources"), list)
    ):
        raise ValueError("folio-sources.json의 version과 sources를 확인해 주세요.")
    catalog = {}
    for row in config["sources"]:
        if not isinstance(row, dict):
            raise ValueError("출처 항목은 객체로 입력해 주세요.")
        path = row.get("path")
        if (
            not isinstance(path, str)
            or not path
            or PurePosixPath(path).as_posix() != path
            or path.startswith("/")
            or "\\" in path
            or ".." in PurePosixPath(path).parts
            or path in catalog
            or PurePosixPath(path).suffix.lower() not in (".md", ".markdown")
        ):
            raise ValueError("출처 목록에 유효한 고유 상대 경로를 입력해 주세요.")
        if (
            row.get("role") not in ("notice", "attachment", "faq")
            or not all(https(row.get(k)) for k in ("publication", "url"))
            or type(row.get("year")) is not int
            or not 1000 <= row["year"] <= 9999
            or not isinstance(row.get("program"), str)
            or not row["program"].strip()
            or not isinstance(row.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        ):
            raise ValueError(
                f"{path}: 공고 주소, 연도, 사업명, 파일 해시를 확인해 주세요."
            )
        allowed, terms = row.get("companions", []), row.get("terms", [])
        if not isinstance(row.get("scope", ""), str):
            raise ValueError(f"{path}: 사업 절 이름을 확인해 주세요.")
        if not isinstance(allowed, list) or not all(https(u) for u in allowed):
            raise ValueError(f"{path}: 공식 첨부 목록에 HTTPS 주소를 입력해 주세요.")
        if not isinstance(terms, list) or not all(
            isinstance(t, str) and 2 <= len(t.strip()) <= 80 for t in terms
        ):
            raise ValueError(f"{path}: 연결 기준어를 확인해 주세요.")
        if path in docs and docs[path]["version"] != row["sha256"]:
            raise ValueError(
                f"{path}: 등록된 원문 해시와 다릅니다. 출처와 판본을 확인해 주세요."
            )
        catalog[path] = row
    return catalog


def publication(row):
    return [row["publication"], row["year"], row["program"]]


def bundles(catalog, files):
    result = {}
    for path, root in catalog.items():
        if root["role"] != "notice" or path not in files:
            continue
        identity = publication(root)
        members = {}
        seen = set()
        for child_path, record in catalog.items():
            if (
                record["role"] == "notice"
                or child_path not in files
                or publication(record) != identity
                or record["url"] not in root.get("companions", [])
                or record["url"] == root["url"]
            ):
                continue
            if record["url"] in seen:
                raise ValueError("같은 공식 첨부를 두 파일에 중복 등록했습니다.")
            seen.add(record["url"])
            members[child_path] = {
                "url": record["url"],
                "version": files[child_path],
                "role": record["role"],
                "scope": record.get("scope", ""),
            }
        result[path] = {
            "identity": identity,
            "terms": sorted(set(root.get("terms", []))),
            "members": members,
        }
    return result


# The tracked term must occur in the selected rule (or its heading) and in
# the same clause as an operative restriction, not just somewhere in the FAQ.
LIMIT = re.compile(
    r"(?:집행|지급|구매|신청|지원|제출)[이가은는을를]?\s*(?:불가|금지)|면제|적용\s*(?:예외|제외)"
)


def has_term(text, term):
    return bool(
        re.search(
            r"(?<![\w])"
            + r"\s*".join(map(re.escape, term.split()))
            + r"(?=$|[\W]|[은는이가을를의에만](?:\s|$))",
            text,
            re.I,
        )
    )


def restricted(text, terms):
    clean = re.sub(r"\x60+[^\x60]*\x60+", "", text)
    for clause in re.split(r"[.!?;。]|\b(?:단|다만|반면)[, ]|하지만", clean):
        limit = LIMIT.search(clause)
        if limit and not re.search(
            r"(?:면제|제외|예외|불가)\s*(?:대상이\s*아|가?\s*아[님니]|않|없|하지\s*않)",
            clause,
        ):
            if any(has_term(clause[: limit.start()], t) for t in terms):
                return True
    return False


def evidence(selected, root_sections, bundle, edition):
    found = {}
    if not bundle:
        return found
    idx = selected.get("unit")
    anchor = units(selected)[idx]["quote"] if idx is not None else selected["quote"]
    terms = [
        t
        for t in bundle["terms"]
        if has_term(selected["topic"].split(" / ")[-1] + " " + anchor, t)
    ]
    ref = rule_reference(selected, root_sections)
    # A bare #fragment in an attachment addresses that attachment, not the notice.
    ref = (None, ref[1], ref[2]) if ref and ref[1] else None
    scope, audience = selected.get("scope", ""), compact(selected.get("audience", ""))
    for path, row in bundle["members"].items():
        for section in edition(path, row["version"], companion=True):
            topic = section["topic"]
            coverage = row["scope"] or topic
            if scope and coverage != scope and not coverage.startswith(scope + " / "):
                continue
            for p in paragraphs(section):
                text = p["quote"].lstrip(" \t☞※•*-")
                if not ((ref and cites_rule(text, ref)) or restricted(text, terms)):
                    continue
                if audience:
                    subject = SUBJECT.match(text)
                    if (
                        not subject
                        or re.search(
                            r"\S+(?:은|는|의\s*경우)(?=\s)", text[subject.end() :]
                        )
                        or audience
                        not in {
                            compact(x)
                            for x in re.split(r",|·|\s및\s|\s또는\s", subject[1])
                        }
                    ):
                        continue
                    text = text[subject.end() :]
                item = excerpt(section, p)
                item.update(
                    section=topic,
                    publication=bundle["identity"][0],
                    year=bundle["identity"][1],
                    program=bundle["identity"][2],
                    source_url=row["url"],
                    role=row["role"],
                )
                found[
                    row["url"],
                    topic,
                    normalized(text),
                    tuple(sorted(item["links"].items())),
                ] = item
    return found


def compare(selected, root_before, root_after, current, change, edition):
    baseline = selected.get("publication_bundle")
    if not baseline:
        return change
    if not current or baseline["identity"] != current["identity"]:
        current = {**baseline, "members": {}}
    if baseline == current:
        return change
    old = evidence(selected, root_before, baseline, edition)
    new = evidence(selected, root_after, current, edition)
    added = [x for k, x in new.items() if k not in old]
    removed = [x for k, x in old.items() if k not in new]
    if not (added or removed):
        return change
    if not change:
        now = next(s for s in root_after if s["topic"] == selected["topic"])
        idx = selected.get("unit")
        before = units(selected)[idx] if idx is not None else None
        after = locate(selected, now, idx)[0] if idx is not None else None
        change = {
            "reason": "exception",
            "before": excerpt(selected, before),
            "after": excerpt(now, after),
            "exceptions": {"added": [], "removed": []},
        }
    change["exceptions"]["added"].extend(added)
    change["exceptions"]["removed"].extend(removed)
    change["external"] = True
    change["scope"] = selected.get("scope", "")
    change["audience"] = selected.get("audience", "")
    return change
