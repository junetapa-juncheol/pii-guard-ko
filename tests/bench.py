"""Build a folder of fake documents with known answers.

Every number is generated at run time with valid checksums, so nothing that
looks like a real identifier is stored in the repository.

    python tests/bench.py OUTDIR      # writes files and OUTDIR/expected.json
"""
import json
import random
import string
import sys
import zipfile
from pathlib import Path

W = (2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5)


class Gen:
    def __init__(self, seed=7):
        self.r = random.Random(seed)

    def digits(self, n):
        return "".join(self.r.choice(string.digits) for _ in range(n))

    def alnum(self, n, chars=string.ascii_letters + string.digits):
        return "".join(self.r.choice(chars) for _ in range(n))

    def _birth(self, lo, hi):
        y = self.r.randint(lo, hi)
        return f"{y % 100:02d}{self.r.randint(1, 12):02d}{self.r.randint(1, 28):02d}", y

    def resident(self, foreign=False, valid=True, born=(1950, 1999)):
        front, year = self._birth(*born)
        g = ("5" if foreign else "1") if year < 2000 else ("7" if foreign else "3")
        while True:
            body = front + g + f"{self.r.randint(0, 95):02d}" + self.digits(3)
            if len(set(body[7:])) > 2:
                break
        s = sum(int(body[i]) * W[i] for i in range(12))
        check = ((13 if foreign else 11) - s % 11) % 10
        if not valid:
            check = (check + 3) % 10
        return f"{front}-{body[6:]}{check}"

    def plain4(self, lo=1000):
        while True:
            d = str(self.r.randint(lo, 9899))
            if len(set(d)) > 2 and not _run(d):
                return d

    def mobile(self, sep="-"):
        while True:
            mid, last = self.plain4(2000), self.plain4()
            if mid != last and not _run(mid + last):
                return f"010{sep}{mid}{sep}{last}"

    def landline(self):
        return f"02-{self.r.randint(300, 899)}-{self.r.randint(2000, 9899)}"

    def card(self, prefix="4", length=16):
        body = prefix + self.digits(length - len(prefix) - 1)
        return body + str(_luhn_digit(body))

    def brn(self):
        while True:
            d = self.digits(9)
            keys = (1, 3, 7, 1, 3, 7, 1, 3, 5)
            t = sum(int(d[i]) * keys[i] for i in range(8))
            last = int(d[8]) * 5
            t += last + last // 10
            d += str((10 - t % 10) % 10)
            if d[:3] != "000":
                return f"{d[:3]}-{d[3:5]}-{d[5:]}"

    def passport(self):
        return "M" + self.digits(3) + self.r.choice("ABCDEFGHJK") + self.digits(4)

    def driver(self):
        return f"{self.r.choice(['11', '12', '13', '21', '26'])}-{self.r.randint(10, 24)}-{self.digits(6)}-{self.digits(2)}"

    def mail_user(self):
        return "zz" + self.alnum(6, string.ascii_lowercase) + self.digits(2)

    def hex(self, n):
        return self.alnum(n, "0123456789abcdef")

    def timestamp_like_resident(self):
        """A 13-digit millisecond timestamp that also passes the resident number check."""
        while True:
            t = str(self.r.randint(1601000000000, 1612280000000))
            if 1 <= int(t[4:6]) <= 28 and t[6] in "1234":
                s = sum(int(t[i]) * W[i] for i in range(12))
                if (11 - s % 11) % 10 == int(t[12]):
                    return t

    def order_like_resident(self):
        return self.resident(valid=True, born=(1920, 1929))

    def id_card_like(self):
        return self.card("4", 16)


# Joined at run time so this source file stays clean for other scanners.
PLACEHOLDER_PHONE = "-".join(("010", "4321", "8765"))
GIT_ADDRESS = "@".join(("git", "github.com"))
FAKE_NAME = "가나다"


def unit(g):
    return f"{g.r.randint(101, 120)}동 {g.r.randint(101, 1504)}호"


def _run(d):
    return d in "0123456789" * 3 or d in "9876543210" * 3


def _luhn_digit(body):
    total = 0
    for i, ch in enumerate(reversed(body)):
        n = int(ch)
        if i % 2 == 0:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return (10 - total % 10) % 10


def spaced(card, groups=(4, 4, 4, 4), sep=" "):
    out, i = [], 0
    for g in groups:
        out.append(card[i:i + g])
        i += g
    return sep.join(out)


class Builder:
    def __init__(self, root):
        self.root = Path(root)
        self.cases = []

    def text(self, name, rows):
        """rows: (line, kinds). None means nothing should be found, "-" means not scored."""
        path = self.root / name
        lines = []
        for i, (line, kinds) in enumerate(rows, 1):
            lines.append(line)
            if kinds == "-":
                continue
            for kind in kinds if isinstance(kinds, tuple) else (kinds,):
                self.cases.append({"file": name, "line": i, "kind": kind})
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def zipped(self, name, members, kind):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as z:
            for member, body in members.items():
                z.writestr(member, body)
        self.cases.append({"file": name, "line": None, "kind": kind})


def build(root, seed=7):
    g = Gen(seed)
    b = Builder(root)
    Path(root).mkdir(parents=True, exist_ok=True)
    photo = f"photo-{g.timestamp_like_resident()}-{g.hex(12)}"
    gmail = f"{g.mail_user()}@gmail.com"

    b.text("memo.txt", [
        ("고객 상담 메모", "-"),
        (f"신청자 주민등록번호 {g.resident()}", "rrn"),
        (f"주민번호:{g.resident().replace('-', '')}", "rrn"),
        (f"자녀 주민등록번호 {g.resident(valid=False, born=(2021, 2023))}", "rrn"),
        (f"외국인등록번호 {g.resident(foreign=True)}", "frn"),
        (f"연락처 {g.mobile()}", "mobile"),
        (f"휴대폰 {g.mobile('.')}", "mobile"),
        (f"해외에서는 +82-10-{g.mobile()[4:]}", "mobile"),
        (f"핸드폰번호{g.mobile('')}", "mobile"),
        (f"사무실 {g.landline()}", "phone"),
        (f"메일 {gmail}", "email"),
        (f"카드번호 {spaced(g.card())}", "card"),
        (f"환불 계좌: 국민은행 {g.digits(6)}-{g.digits(2)}-{g.digits(6)}", "account"),
        (f"사업자등록번호 {g.brn()}", "brn"),
        (f"여권번호 {g.passport()}", "passport"),
        (f"운전면허번호 {g.driver()}", "driver"),
        (f"주소는 상상아파트 {unit(g)}에 있음", "dongho"),
        (f"차량번호 {g.r.randint(10, 99)}가{g.plain4()}", "vehicle"),
        ("예: 010-1234-5678 형식으로 입력", None),
        ("주민번호는 900101-1****** 처럼 가려서 적음", None),
        ("전화 010-XXXX-XXXX", None),
        ("발행일 2026-10-21 · 버전 3.12.4 · 빌드 20261021", None),
        (f"주문번호 {g.order_like_resident()}", None),
        ("고객센터 1588-0000", None),
        ("가격 1,234,500원 · 좌표 37.5665, 126.9780", None),
        ("시험 카드 4242 4242 4242 4242", None),
        (f"커밋 {g.hex(40)}", None),
        (f"요청 {g.hex(8)}-{g.hex(4)}-4{g.hex(3)}-a{g.hex(3)}-{g.hex(12)}", None),
    ])

    b.text("page.html", [
        ("<!doctype html>", "-"),
        ("<html><head>", "-"),
        (f'<meta property="og:image" content="https://images.unsplash.com/{photo}?w=1200">', None),
        ('<script type="application/ld+json">{"image": "https:\\/\\/images.unsplash.com\\/' + photo + '"}</script>', None),
        ("</head><body>", "-"),
        (f'<img src="https://images.unsplash.com/{photo}?w=800" alt="카페">', None),
        (f'<img srcset="https://images.unsplash.com/{photo}?w=400 400w, https://images.unsplash.com/{photo}?w=800 800w">', None),
        (f"<div style=\"background:url('https://images.unsplash.com/{photo}')\"></div>", None),
        ('<input type="tel" name="phone" placeholder="010-0000-0000">', None),
        ('<input type="text" name="mobile" placeholder="010-1234-5678">', None),
        (f'<input type="tel" placeholder="{PLACEHOLDER_PHONE}" aria-describedby="hint">', None),
        (f'<p>문의 <a href="tel:{g.mobile()}">전화</a></p>', "mobile"),
        (f"<table><tr><td>가나다</td><td>{g.mobile()}</td></tr></table>", "mobile"),
        (f'<p><a href="mailto:{g.mail_user()}@hanmail.net">메일 보내기</a></p>', "email"),
        ("<p>아이콘은 icon@2x.png 파일</p>", None),
        ("</body></html>", "-"),
    ])

    b.text("data.json", [
        ("{", "-"),
        (f'  "phone": "{g.mobile()}",', "mobile"),
        (f'  "email": "{g.mail_user()}@hanmail.net",', "email"),
        (f'  "created_at": {g.timestamp_like_resident()},', None),
        (f'  "order_id": "{g.id_card_like()}",', None),
        (f'  "photo": "https://images.unsplash.com/{photo}",', None),
        ('  "placeholder": "010-0000-0000",', None),
        (f'  "card": "{spaced(g.card("52"), sep="-")}",', "card"),
        (f'  "sha256": "{g.hex(64)}"', None),
        ("}", "-"),
    ])

    b.text("customers.csv", [
        ("이름,휴대폰,이메일,여권번호,가입일", "-"),
        (f"가나다,{g.mobile()},{g.mail_user()}@gmail.com,{g.passport()},2026-10-01", ("mobile", "email", "passport")),
        (f"라마바,{g.mobile('')},{g.mail_user()}@gmail.com,{g.passport()},2026-10-02", ("mobile", "email", "passport")),
        ("예시,010-0000-0000,user@example.com,M000A0000,2026-01-01", None),
    ])

    b.text("settings.py", [
        (f'ADMIN_PHONE = "{g.mobile()}"', "mobile"),
        (f'API_KEY = "sk-ant-api03-{g.alnum(80)}"', "key"),
        (f'GITHUB_TOKEN = "ghp_{g.alnum(36)}"', "key"),
        (f'AWS_ACCESS_KEY_ID = "AKIA{g.alnum(16, string.ascii_uppercase + string.digits)}"', "key"),
        ('PLACEHOLDER_KEY = "sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx"', None),
        ('VERSION = "1.10.2"', None),
    ])

    b.text("NOTES", [
        (f"담당자 메일 {g.mail_user()}@gmail.com", "email"),
        (f"개인 번호 {g.mobile(' ')}", "mobile"),
        (f"주민등록번호 {g.resident()}", "rrn"),
    ])

    b.text(".env", [
        (f"OPENAI_API_KEY=sk-proj-{g.alnum(48)}", "key"),
        (f"SLACK_BOT_TOKEN=xoxb-{g.digits(12)}-{g.digits(12)}-{g.alnum(24)}", "key"),
        (f"GOOGLE_API_KEY=AIza{g.alnum(35)}", "key"),
        ("DATABASE_URL=postgresql://user:password@localhost:5432/app", None),
    ])

    b.text("app.log", [
        (f"2026-10-21 10:31:02 INFO signed in user={g.mail_user()}@gmail.com", "email"),
        (f"2026-10-21 10:31:05 DEBUG request_id={g.timestamp_like_resident()} took 35ms", None),
        (f"2026-10-21 10:31:06 DEBUG trace={g.hex(32)}", None),
    ])

    b.text("README.md", [
        ("# 카페 소개", "-"),
        (f"![카페](https://images.unsplash.com/{photo}?w=800)", None),
        (f"문의는 {g.mail_user()}@gaga-corp.co.kr 로", "email"),
        ("| 휴대폰 | `010-****-1234` |", None),
    ])

    b.text("script.js", [
        (f'const phone = "{g.mobile()}";', "mobile"),
        ("const re = /010-\\d{4}-\\d{4}/;", None),
        ("// e.g. 010-1234-5678", None),
    ])

    b.text("Form.jsx", [
        (f'<input name="tel" placeholder="{PLACEHOLDER_PHONE}" />', None),
        (f'<p>대표 연락처 {g.mobile()}</p>', "mobile"),
    ])

    b.text("notes.yaml", [
        (f"contact: {g.mobile()}", "mobile"),
        ("build: 20261021", None),
    ])

    runs = "".join(f"<w:r><w:t>{t}</w:t></w:r>" for t in ("연락처 ", g.mobile()))
    doc = ('<?xml version="1.0" encoding="UTF-8"?><w:document><w:body>'
           f"<w:p>{runs}</w:p><w:p><w:r><w:t>예: 010-1234-5678</w:t></w:r></w:p>"
           "</w:body></w:document>")
    b.zipped("report.docx", {"[Content_Types].xml": "<Types/>", "word/document.xml": doc}, "mobile")

    shared = ('<?xml version="1.0" encoding="UTF-8"?><sst><si><t>이름</t></si><si><t>주민등록번호</t></si>'
              f"<si><t>가나다</t></si><si><t>{g.resident()}</t></si></sst>")
    sheet = ('<?xml version="1.0" encoding="UTF-8"?><worksheet><sheetData>'
             '<row r="1"><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
             '<row r="2"><c t="s"><v>2</v></c><c t="s"><v>3</v></c></row></sheetData></worksheet>')
    b.zipped("list.xlsx", {"xl/sharedStrings.xml": shared, "xl/worksheets/sheet1.xml": sheet}, "rrn")

    return b.cases


if __name__ == "__main__":
    out = Path(sys.argv[1])
    cases = build(out)
    answers = out.with_name(out.name + ".expected.json")
    answers.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(cases)} cases -> {out}")
