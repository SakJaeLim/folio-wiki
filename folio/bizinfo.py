"""Read one official Bizinfo listing and the download links owned by that listing."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOST = "www.bizinfo.go.kr"
DETAIL = "/sii/siia/selectSIIA200Detail.do"
DOWNLOAD = "/cmm/fms/fileDown.do"
NOTICE_ID = re.compile(r"PBLN_\d{12,15}")
FILE_SIZE = 24 << 20


def notice_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("기업마당 공고 상세 주소를 입력해 주세요.")
    u = urlsplit(value.strip())
    ids = parse_qs(u.query).get("pblancId", [])
    if (
        u.scheme != "https"
        or u.netloc.lower() not in (HOST, "bizinfo.go.kr")
        or u.path != DETAIL
        or len(ids) != 1
        or not NOTICE_ID.fullmatch(ids[0])
    ):
        raise ValueError("기업마당 공고 상세 주소(pblancId)가 필요합니다.")
    return f"https://{HOST}{DETAIL}?pblancId={ids[0]}"


def download_link(page, href):
    u = urlsplit(urljoin(page, href))
    q = parse_qs(u.query, keep_blank_values=True)
    if (
        u.scheme != "https"
        or u.netloc.lower() != HOST
        or u.path != DOWNLOAD
        or u.fragment
        or set(q) - {"atchFileId", "fileSn", "downloadToken"}
        or any(len(v) != 1 for v in q.values())
    ):
        return None
    fid = q.get("atchFileId", [""])[0]
    seq = q.get("fileSn", [""])[0]
    if not re.fullmatch(r"FILE_\d{1,20}", fid) or not re.fullmatch(r"\d{1,4}", seq):
        return None
    stable = f"https://{HOST}{DOWNLOAD}?" + urlencode(
        {"atchFileId": fid, "fileSn": seq}
    )
    return stable, u.geturl()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def fetch(url, referer, limit):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": referer})
    try:
        with build_opener(NoRedirect()).open(req, timeout=20) as response:
            data = response.read(limit + 1)
    except HTTPError as exc:
        raise ValueError(f"공식 사이트가 HTTP {exc.code}을 반환했습니다.") from None
    if len(data) > limit:
        raise ValueError("공식 자료가 다운로드 크기 한도를 넘었습니다.")
    return data


@dataclass
class File:
    name: str
    group: str
    stable: str
    signed: str


class Listing(HTMLParser):
    """Use section ancestry rather than all hyperlinks in the HTML document."""

    void = frozenset(
        (
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        )
    )

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.stack = []
        self.title = ""
        self.group = ""
        self.row = None
        self.files = []

    def handle_starttag(self, tag, attrs):
        if tag in self.void:
            return
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        flags = set(self.stack[-1][1]) if self.stack else set()
        if "support_project_detail" in classes:
            flags.add("detail")
        if "detail" in flags:
            if tag == "h2" and "title" in classes:
                flags.add("title")
            if "attached_file_list" in classes:
                flags.add("list")
        if "list" in flags:
            if tag == "h3":
                flags.add("group")
                self.group = ""
            if tag == "li":
                self.row = {"name": "", "href": ""}
            if self.row is not None:
                if "file_name" in classes:
                    flags.add("name")
                if tag == "a" and "icon_download" in classes:
                    self.row["href"] = attrs.get("href", "")
        self.stack.append((tag, flags))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] != tag:
                continue
            if tag == "li" and self.row is not None:
                row = self.row
                self.row = None
                pair = download_link(self.page, row["href"])
                name = " ".join(row["name"].split())
                if not pair or not name:
                    raise ValueError(
                        "공식 첨부의 파일명 또는 다운로드 주소를 확인할 수 없습니다."
                    )
                self.files.append(File(name, self.group.strip(), *pair))
            del self.stack[i:]
            break

    def handle_data(self, data):
        flags = self.stack[-1][1] if self.stack else ()
        if "title" in flags:
            self.title += data
        if "group" in flags:
            self.group += data
        if "name" in flags and self.row is not None:
            self.row["name"] += data


def discover(url, read=fetch):
    page = notice_url(url)
    listing = Listing(page)
    listing.feed(read(page, page, 2 << 20).decode("utf-8-sig"))
    title = " ".join(listing.title.split())
    files = listing.files
    if (
        not title
        or not 1 <= len(files) <= 30
        or len({f.stable for f in files}) != len(files)
        or sum(f.group == "본문출력파일" for f in files) != 1
    ):
        raise ValueError("이 공고의 본문 파일 또는 첨부 목록을 확정할 수 없습니다.")
    return page, title, files


YEAR = re.compile(r"(?<!\d)(20\d{2})(?:\s*년|\b|_)")
TRACK = re.compile(r"사내\s*벤처|로컬\s*크리에이터|재도전|생애\s*최초")


def cover_conflict(title, parts):
    # Only the title preceding a FAQ heading identifies the edition. Dates and
    # programme names in the answers may legitimately refer to earlier years.
    first = " ".join(parts[0][1].split())[:240]
    header = re.match(r"(.{0,170}?)(?:질의\s*응답|FAQ|자주\s*묻)", first, re.I)
    if not header:
        return ""
    heading = header[1]
    year = YEAR.search(title)
    years = {2000 + int(n) for n in re.findall(r"(?<!\d)(?:20)?(\d{2})\s*년", heading)}
    if year and years and years != {int(year[1])}:
        return "FAQ 표지와 공고 연도가 다름"
    return identity_conflict(title, heading)


def identity_conflict(title, name):
    def compact(value):
        return re.sub(r"[\W_]+", "", value)

    heading = compact(title)
    if any(compact(m[0]) not in heading for m in TRACK.finditer(name)):
        return "공고명과 다른 세부 사업"
    programs = re.findall(r"[가-힣]{2,}(?:패키지|펠로우십|바우처)", name)
    if any(program not in heading for program in programs):
        return "공고명과 다른 사업명"
    return ""


def classify(title, file):
    years = set(YEAR.findall(title))
    declared = set(YEAR.findall(file.name))
    if len(years) != 1 or (declared and declared != years):
        return "제외", "공고와 연도가 다르거나 연도를 확정할 수 없음"
    conflict = identity_conflict(title, file.name)
    if conflict:
        return "제외", conflict
    if file.group == "본문출력파일":
        return "본문", ""
    if file.group != "첨부파일":
        return "제외", "분류를 확인할 수 없음"
    if re.search(r"질의\s*응답|FAQ|Q\s*&\s*A|자주\s*묻", file.name, re.I):
        return "FAQ", ""
    if re.search(r"양식|매뉴얼|소개자료", file.name):
        return "참고", "양식 또는 참고자료"
    return "첨부", ""
