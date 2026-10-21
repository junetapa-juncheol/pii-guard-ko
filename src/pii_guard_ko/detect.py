"""Find Korean personal data in a piece of text."""
import bisect
import ipaddress
import re
from dataclasses import dataclass

from . import checks
from .keys import find_keys

SURE, SUSPECT = 2, 1
IGNORE_MARK = "pii-guard-ko: ignore"
A = re.ASCII

LABELS = {
    "rrn": "주민등록번호", "frn": "외국인등록번호", "mobile": "휴대폰번호", "phone": "유선전화",
    "email": "이메일", "card": "카드번호", "account": "계좌번호", "brn": "사업자등록번호",
    "passport": "여권번호", "driver": "운전면허번호", "vehicle": "차량번호", "dongho": "동·호수",
    "address": "도로명주소", "name": "이름 칸", "birth": "생년월일 칸", "ip": "IP 주소",
    "key": "API 키·토큰", "jwt": "JWT 토큰", "gps": "사진 GPS", "photo_meta": "사진 개인 메타",
}
ORDER = ["key", "jwt", "rrn", "frn", "card", "mobile", "account", "brn", "driver", "passport",
         "phone", "email", "ip", "vehicle", "dongho", "address", "name", "birth"]


@dataclass
class Finding:
    kind: str
    start: int
    end: int
    level: int
    reason: str
    value: str = ""
    line: int = 0
    col: int = 0

    @property
    def label(self):
        return LABELS.get(self.kind, self.kind)


def _words(*ws):
    return re.compile("|".join(ws), re.I)


CTX = {
    "rrn": _words("주민", "등록번호", "생년월일", "resident", r"\brrn\b", "jumin"),
    "frn": _words("외국인", "등록번호", "foreigner", r"\bfrn\b", "alien"),
    "mobile": _words("전화", "연락", "휴대", "핸드폰", "폰", "문의", r"\btel\b", "phone", "mobile",
                     r"\bcell\b", r"\bhp\b", "번호"),
    "card": _words("카드", "card", "결제", "신용", "체크", r"\bvisa\b", "master"),
    "account": _words("계좌", "입금", "송금", "예금주", "은행", "뱅크", "account", "bank", "국민", "신한",
                      "우리", "하나", "농협", "기업", "카카오", "토스", "새마을", "우체국", "신협", "수협",
                      "SC제일", "씨티"),
    "account_raw": _words("계좌", "입금", "송금", "예금주", "account"),
    "brn": _words("사업자", "business", r"\bbrn\b", r"\btax\b"),
    "passport": _words("여권", "passport"),
    "driver": _words("면허", "licen[cs]e"),
    "vehicle": _words("차량", "번호판", "차번호", "자동차", "주차", "vehicle", r"\bcar\b"),
}
NOT_PERSONAL = _words("주문", "송장", "운송장", "접수", "예약", "order", "invoice", "tracking", "request",
                      "trace", r"_id\b", r"\bid\b", r"\bts\b", "time", "created", "updated", "epoch",
                      r"\bseq\b", "isbn", r"\bsku\b")
EXAMPLE = _words("예시", r"예\s?[:)]", r"e\.g\.", r"\bex[):]", "샘플", "sample", "placeholder", "형식",
                 "dummy", "더미")

URL_RE = re.compile(
    r"(?:https?|ftp)://[^\s\"'<>`]+"
    r"|https?:\\/\\/[^\s\"'<>`]+"
    r"|\bwww\.[^\s\"'<>()`]+"
    r"|url\(\s*['\"]?[^)'\"\s]+"
    r"|data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+", re.I)

KEEP_ATTR = re.compile(r"""\b(href|content|alt|title|value|aria-label|data-[\w-]+)\s*=\s*("[^"]*"|'[^']*')""", re.I)
BLOCK_RE = re.compile(r"<(script|style)\b([^>]*)>(.*?)</\1\s*>", re.S | re.I)
TAG_RE = re.compile(r"<[A-Za-z/!?][^<>]*>")


def html_view(text):
    """Blank out markup but keep text, comments and some attribute values in place.

    Script bodies stay so keys and mail addresses inside them can still be found.
    """
    out = list(text)
    code = []

    def blank(a, b):
        for i in range(a, b):
            if out[i] not in "\r\n":
                out[i] = " "

    for m in BLOCK_RE.finditer(text):
        if m.group(1).lower() == "style":
            blank(m.start(), m.end())
            continue
        blank(m.start(), m.start(3))
        blank(m.end(3), m.end())
        if "ld+json" not in m.group(2).lower():
            code.append(m.span(3))
    view = "".join(out)
    for m in TAG_RE.finditer(view):
        if view.startswith("<!--", m.start()) or any(a <= m.start() < b for a, b in code):
            continue
        pos = m.start()
        for attr in KEEP_ATTR.finditer(m.group(0)):
            a = m.start() + attr.start(2) + 1
            blank(pos, a)
            pos = m.start() + attr.end(2) - 1
        blank(pos, m.end())
    return "".join(out), code


def _ident(ch):
    return ch.isascii() and (ch.isalnum() or ch == "_")


class Doc:
    def __init__(self, text, kind="text"):
        self.raw = text
        self.kind = kind
        self.code = []
        if kind == "html":
            self.text, self.code = html_view(text)
        else:
            self.text = text
        self.newlines = [m.start() for m in re.finditer("\n", text)]
        self.urls = [m.span() for m in URL_RE.finditer(self.text)]
        self.url_starts = [a for a, _ in self.urls]
        self.header = self._header() if kind in ("csv", "tsv") else None

    def _header(self):
        sep = "\t" if self.kind == "tsv" else ","
        first = self.text.split("\n", 1)[0]
        return [c.strip().strip('"') for c in first.split(sep)]

    def position(self, i):
        n = bisect.bisect_left(self.newlines, i)
        start = self.newlines[n - 1] + 1 if n else 0
        return n + 1, i - start + 1

    def line_of(self, i):
        a = self.raw.rfind("\n", 0, i) + 1
        b = self.raw.find("\n", i)
        return self.raw[a:b if b >= 0 else len(self.raw)]

    def column_name(self, i):
        if not self.header:
            return ""
        a = self.text.rfind("\n", 0, i) + 1
        if a == 0:
            return ""
        sep = "\t" if self.kind == "tsv" else ","
        idx = self.text.count(sep, a, i)
        return self.header[idx] if idx < len(self.header) else ""

    def window(self, s, e, before=30, after=12):
        return self.text[max(0, s - before):s] + " " + self.text[e:e + after] + " " + self.column_name(s)

    def has(self, s, e, words, before=30, after=12):
        return bool(words.search(self.window(s, e, before, after)))

    def example(self, s):
        a = self.text.rfind("\n", 0, s) + 1
        return bool(EXAMPLE.search(self.text[max(a, s - 14):s]))

    def in_url(self, s, e):
        i = bisect.bisect_right(self.url_starts, s) - 1
        return i >= 0 and e <= self.urls[i][1]

    def in_code(self, s):
        return any(a <= s < b for a, b in self.code)

    def glued(self, s, e):
        t = self.text
        b1 = t[s - 1] if s > 0 else ""
        b2 = t[s - 2] if s > 1 else ""
        a1 = t[e] if e < len(t) else ""
        a2 = t[e + 1] if e + 1 < len(t) else ""
        if (b1 and _ident(b1)) or (a1 and _ident(a1)):
            return True
        if b1 and b1 in "-_/" and b2 and _ident(b2):
            return True
        if b1 == "." and b2.isdigit():
            return True
        if a1 and a1 in "-_/" and a2 and _ident(a2):
            return True
        if a1 == "." and a2 and a2.isascii() and a2.isalnum():
            return True
        return False

    def skip_number(self, s, e):
        return self.in_url(s, e) or self.glued(s, e) or self.in_code(s)


def _digits(s):
    return re.sub(r"[^0-9]", "", s)


RRN_RE = re.compile(r"(?<![0-9])([0-9]{6})(\s?-\s?)?([0-9]{7})(?![0-9])", A)


def rule_rrn(doc):
    for m in RRN_RE.finditer(doc.text):
        s, e = m.span()
        d = m.group(1) + m.group(3)
        kind = "frn" if d[6] in "5678" else "rrn"
        if doc.skip_number(s, e) or checks.birth_date(d) is None:
            continue
        if checks.fake_digits(d[7:]) or doc.example(s):
            continue
        ctx = doc.has(s, e, CTX[kind])
        if not ctx and doc.has(s, e, NOT_PERSONAL, 25, 0):
            continue
        valid = checks.rrn_ok(d) if kind == "rrn" else checks.frn_ok(d)
        hyphen = bool(m.group(2))
        if valid:
            yield kind, s, e, (SURE if hyphen or ctx else SUSPECT), "체크섬 맞음"
        elif hyphen and ctx:
            yield kind, s, e, SURE, "형식+문맥(2020.10 뒤 번호는 체크섬 없음)"
        elif hyphen or ctx:
            yield kind, s, e, SUSPECT, "형식만"


MOBILE_RE = re.compile(
    r"(?<![0-9A-Za-z_+])(\+82[-. ]?(?:\(0\))?1[016789]|01[016789])([-. ]?)([0-9]{3,4})\2([0-9]{4})(?![0-9A-Za-z_])", A)


def rule_mobile(doc):
    for m in MOBILE_RE.finditer(doc.text):
        s, e = m.span()
        mid, last = m.group(3), m.group(4)
        if doc.skip_number(s, e) or mid[0] == "0" or checks.fake_phone(mid, last) or doc.example(s):
            continue
        if m.group(2) or m.group(1).startswith("+"):
            yield "mobile", s, e, SURE, "구분자 있는 휴대폰"
        elif doc.has(s, e, CTX["mobile"]):
            yield "mobile", s, e, SURE, "붙은 11자리+문맥"
        elif not doc.has(s, e, NOT_PERSONAL, 25, 0):
            yield "mobile", s, e, SUSPECT, "붙은 11자리"


PHONE_RE = re.compile(
    r"(?<![0-9A-Za-z_])\(?(02|03[1-3]|04[1-4]|05[1-5]|06[1-4]|070)(?:\)\s?|[-. ])([0-9]{3,4})[-. ]([0-9]{4})(?![0-9A-Za-z_])", A)


def rule_phone(doc):
    for m in PHONE_RE.finditer(doc.text):
        s, e = m.span()
        mid, last = m.group(2), m.group(3)
        if doc.skip_number(s, e) or mid[0] in "01" or checks.fake_phone(mid, last) or doc.example(s):
            continue
        yield "phone", s, e, SUSPECT, "유선(기관·가게일 수 있음)"


EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+", A)
FREE_MAIL = {"gmail.com", "naver.com", "daum.net", "hanmail.net", "kakao.com", "nate.com", "hotmail.com",
             "outlook.com", "live.com", "icloud.com", "me.com", "yahoo.com", "yahoo.co.kr", "proton.me",
             "protonmail.com"}
DEMO_DOMAINS = re.compile(r"(^|\.)(example|test|domain|email|sample|yourdomain|company|foo|bar|localhost)"
                          r"\.(com|org|net|co\.kr|kr)$|\.(example|test|invalid|localhost|local)$")
DEMO_LOCAL = {"you", "your", "user", "username", "name", "me", "someone", "abc", "test", "example",
              "foo", "bar", "hong", "gildong", "email", "id", "mail"}
ROLE_LOCAL = re.compile(r"^(no-?reply|do-?not-?reply|support|privacy|abuse|info|help|contact|admin|webmaster|"
                        r"security|press|hello|sales|team|service|cs|feedback|legal|dpo|notifications?|bounce|"
                        r"postmaster|hostmaster|git|mailer-daemon)$")
FILE_TLDS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "avif", "ico", "js", "mjs", "css", "map", "json",
             "html", "pdf", "zip", "py", "ts"}
TECH_DOMAINS = {"users.noreply.github.com", "libssh.org", "openssh.com"}


def rule_email(doc):
    for m in EMAIL_RE.finditer(doc.text):
        s, e = m.span()
        value = m.group(0).lower()
        local, domain = value.split("@", 1)
        tld = domain.rsplit(".", 1)[-1]
        if not tld.isalpha() or len(tld) < 2 or tld in FILE_TLDS:
            continue
        if doc.text[s - 1:s] in ("/", "&") or DEMO_DOMAINS.search(domain) or domain in TECH_DOMAINS:
            continue
        if local in DEMO_LOCAL or "noreply" in domain or "no-reply" in domain:
            continue
        free = domain in FREE_MAIL
        if ROLE_LOCAL.match(local) and not free:
            continue
        if free:
            yield "email", s, e, SURE, "개인 메일 도메인"
        else:
            yield "email", s, e, SUSPECT, "회사·기관 도메인"


CARD_RE = re.compile(
    r"(?<![0-9A-Za-z_.\-])(?:[0-9]{4}([- ])[0-9]{4}\1[0-9]{4}\1[0-9]{4}(?:\1[0-9]{3})?"
    r"|[0-9]{4}([- ])[0-9]{6}\2[0-9]{4,5}|[0-9]{13,19})(?![0-9A-Za-z_\-])", A)


def rule_card(doc):
    for m in CARD_RE.finditer(doc.text):
        s, e = m.span()
        d = _digits(m.group(0))
        if doc.skip_number(s, e) or not checks.card_brand(d) or not checks.luhn_ok(d):
            continue
        if d in checks.TEST_CARDS or checks.fake_digits(d[6:]) or doc.example(s):
            continue
        if m.group(1) or m.group(2):
            yield "card", s, e, SURE, "Luhn 맞음+구분자"
        elif doc.has(s, e, CTX["card"]):
            yield "card", s, e, SURE, "Luhn 맞음+문맥"
        elif not doc.has(s, e, NOT_PERSONAL, 25, 0):
            yield "card", s, e, SUSPECT, "Luhn 맞음·붙은 숫자"


ACCOUNT_RE = re.compile(r"(?<![0-9A-Za-z_.\-])[0-9]{2,6}-[0-9]{2,6}-[0-9]{2,7}(?:-[0-9]{1,3})?(?![0-9A-Za-z_\-])", A)
ACCOUNT_RAW_RE = re.compile(r"(?<![0-9A-Za-z_.\-])[0-9]{10,14}(?![0-9A-Za-z_\-])", A)


PHONE_SHAPE = re.compile(r"0(?:1[016789]|2|[3-6][1-5]|[578]0[0-9]?)-[0-9]{3,4}-[0-9]{4}", A)


def rule_account(doc):
    for m in ACCOUNT_RE.finditer(doc.text):
        s, e = m.span()
        d = _digits(m.group(0))
        if not 10 <= len(d) <= 14 or doc.skip_number(s, e) or checks.fake_digits(d) or doc.example(s):
            continue
        if PHONE_SHAPE.fullmatch(m.group(0)):
            continue
        if doc.has(s, e, CTX["account"], 25, 10):
            yield "account", s, e, SURE, "계좌+은행 문맥"
    for m in ACCOUNT_RAW_RE.finditer(doc.text):
        s, e = m.span()
        if doc.skip_number(s, e) or checks.fake_digits(m.group(0)) or doc.example(s):
            continue
        if doc.has(s, e, CTX["account_raw"], 20, 0):
            yield "account", s, e, SUSPECT, "붙은 숫자+계좌 문맥"


BRN_RE = re.compile(r"(?<![0-9A-Za-z_.\-])(?:[0-9]{3}-[0-9]{2}-[0-9]{5}|[0-9]{10})(?![0-9A-Za-z_\-])", A)


def rule_brn(doc):
    for m in BRN_RE.finditer(doc.text):
        s, e = m.span()
        d = _digits(m.group(0))
        if doc.skip_number(s, e) or checks.fake_digits(d) or not checks.brn_ok(d):
            continue
        if "-" in m.group(0) or doc.has(s, e, CTX["brn"]):
            yield "brn", s, e, SUSPECT, "체크섬 맞음(공개된 사업자 정보일 수 있음)"


PASSPORT_RE = re.compile(r"(?<![0-9A-Za-z_])[MSRODmsrod](?:[0-9]{3}[A-Za-z][0-9]{4}|[0-9]{8})(?![0-9A-Za-z_])", A)


def rule_passport(doc):
    for m in PASSPORT_RE.finditer(doc.text):
        s, e = m.span()
        if doc.in_url(s, e) or doc.in_code(s) or checks.fake_digits(_digits(m.group(0))):
            continue
        if doc.has(s, e, CTX["passport"]):
            yield "passport", s, e, SURE, "형식+문맥"


DRIVER_RE = re.compile(
    r"(?<![0-9A-Za-z_])(?:1[1-9]|2[0-68])([- ]?)[0-9]{2}\1([0-9]{6})\1[0-9]{2}(?![0-9A-Za-z_])", A)


def rule_driver(doc):
    for m in DRIVER_RE.finditer(doc.text):
        s, e = m.span()
        if doc.skip_number(s, e) or checks.fake_digits(m.group(2)):
            continue
        if doc.has(s, e, CTX["driver"]):
            yield "driver", s, e, SURE, "형식+문맥"


VH = "가나다라마거너더러머버서어저고노도로모보소오조구누두루무부수우주아바사자배하허호"
REGION = "서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주"
VEHICLE_RE = re.compile(rf"(?<![0-9A-Za-z_])(?:(?:{REGION})\s?)?[0-9]{{2,3}}\s?[{VH}]\s?[0-9]{{4}}(?![0-9A-Za-z_])", A)


PARTICLES = "이가은는을를의에도와과로"
YEAR_GAP = re.compile(r"[가-힣]\s+(?:19|20)[0-9]{2}$")


def rule_vehicle(doc):
    for m in VEHICLE_RE.finditer(doc.text):
        s, e = m.span()
        after = doc.text[e:e + 1]
        if "가" <= after <= "힣" and after not in PARTICLES:
            continue
        if YEAR_GAP.search(m.group(0)):
            continue
        last4 = m.group(0)[-4:]
        if doc.skip_number(s, e) or len(set(last4)) == 1 or doc.example(s):
            continue
        if doc.has(s, e, CTX["vehicle"]):
            yield "vehicle", s, e, SURE, "차량 문맥"
        else:
            yield "vehicle", s, e, SUSPECT, "형식만"


DONGHO_RE = re.compile(r"(?<![0-9])[0-9]{1,4}\s?동\s?[0-9]{1,4}\s?호(?![0-9]|기|선|차)", A)
SIDO = (r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청북|충청남|충북|충남|전라북|전라남|전북|전남|"
        r"경상북|경상남|경북|경남|제주)\S{0,4}")
ADDRESS_RE = re.compile(SIDO + r"\s+\S{1,10}?[시군구]\s+(?:\S{1,10}?[읍면동]\s+)?\S{1,15}?(?:로|길)\s?[0-9]{1,4}"
                        r"(?:-[0-9]{1,4})?(?:번길\s?[0-9]{1,4})?", A)
NAME_RE = re.compile(r"(?:성명|이름|예금주|수취인|받는\s?분|보호자|환자명)\s?[:：]\s?([가-힣]{2,4})(?![가-힣])", A)
LABEL_AFTER = re.compile(r"\s*[:：]")
NOT_NAME_BEFORE = re.compile(r"폴더|파일|제목|채널|계정|모델|변수|태그|브랜드|상품|제품|메뉴|회사|업체|가게|[:<]\s*$")
DEMO_NAMES = {"홍길동", "홍길순", "김철수", "이영희", "김영희", "아무개", "고객님", "회원님", "사용자", "작성자",
              "본인", "없음", "미정", "입력", "비공개", "익명"}
BIRTH_RE = re.compile(r"생년월일\s?[:：]?\s?(?:19|20)?[0-9]{2}[.\-/년\s]{1,2}[0-9]{1,2}[.\-/월\s]{1,2}[0-9]{1,2}일?", A)


def rule_places(doc):
    for m in DONGHO_RE.finditer(doc.text):
        if not doc.in_code(m.start()):
            yield "dongho", m.start(), m.end(), SURE, "동·호"
    for m in ADDRESS_RE.finditer(doc.text):
        if not doc.in_code(m.start()):
            yield "address", m.start(), m.end(), SUSPECT, "도로명+건물번호(기관 주소일 수 있음)"
    for m in NAME_RE.finditer(doc.text):
        s, e = m.span()
        name = m.group(1)
        if doc.in_code(s) or NOT_NAME_BEFORE.search(doc.text[max(0, s - 8):s]) or LABEL_AFTER.match(doc.text, e):
            continue
        if name in DEMO_NAMES or "OO" in name or name.endswith(("씨", "님")):
            continue
        yield "name", s, e, SUSPECT, "이름 칸"
    for m in BIRTH_RE.finditer(doc.text):
        if not doc.in_code(m.start()):
            yield "birth", m.start(), m.end(), SUSPECT, "생년월일 칸"


IP_RE = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])", A)
PUBLIC_DNS = {"8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "208.67.222.222", "208.67.220.220"}


def rule_ip(doc):
    for m in IP_RE.finditer(doc.text):
        s, e = m.span()
        value = m.group(0)
        if doc.skip_number(s, e) or value in PUBLIC_DNS:
            continue
        if sum(len(x) == 1 for x in value.split(".")) >= 3:
            continue
        try:
            if not ipaddress.ip_address(value).is_global:
                continue
        except ValueError:
            continue
        yield "ip", s, e, SUSPECT, "공인 IP"


def rule_keys(doc):
    yield from ((kind, s, e, lvl, why) for s, e, kind, lvl, why in find_keys(doc.text))


RULES = [rule_keys, rule_rrn, rule_mobile, rule_phone, rule_email, rule_card, rule_account,
         rule_brn, rule_passport, rule_driver, rule_vehicle, rule_places, rule_ip]


def scan_doc(doc):
    found = []
    for rule in RULES:
        for kind, s, e, level, why in rule(doc):
            found.append(Finding(kind, s, e, level, why))
    rank = {k: i for i, k in enumerate(ORDER)}
    found.sort(key=lambda f: (-f.level, -(f.end - f.start), rank[f.kind]))
    kept = []
    for f in found:
        if any(f.start < k.end and k.start < f.end for k in kept):
            continue
        if IGNORE_MARK in doc.line_of(f.start):
            continue
        f.value = doc.raw[f.start:f.end]
        f.line, f.col = doc.position(f.start)
        kept.append(f)
    kept.sort(key=lambda f: f.start)
    return kept


def scan_text(text, kind="text"):
    """Scan a string. kind is 'text', 'html', 'csv' or 'tsv'."""
    return scan_doc(Doc(text, kind))
