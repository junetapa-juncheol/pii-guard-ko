import pytest

from bench import FAKE_NAME, GIT_ADDRESS, PLACEHOLDER_PHONE, Gen, spaced, unit
from pii_guard_ko import scan_text

g = Gen(11)

FOUND = [
    ("rrn", 2, f"주민등록번호 {g.resident()}"),
    ("rrn", 2, f"주민번호 {g.resident(valid=False, born=(2021, 2023))}"),
    ("rrn", 2, g.resident()),
    ("rrn", 1, g.resident().replace("-", "")),
    ("frn", 2, f"외국인등록번호 {g.resident(foreign=True)}"),
    ("mobile", 2, f"연락처 {g.mobile()}"),
    ("mobile", 2, f"연락처{g.mobile('')}"),
    ("mobile", 2, f"+82 10 {g.mobile(' ')[4:]}"),
    ("mobile", 1, f"x {g.mobile('')} y"),
    ("phone", 1, f"사무실 {g.landline()}"),
    ("email", 2, f"메일 {g.mail_user()}@gmail.com"),
    ("email", 1, f"메일 {g.mail_user()}@gaga-corp.co.kr"),
    ("card", 2, f"카드 {spaced(g.card('4'))}"),
    ("card", 2, f"card {spaced(g.card('37', 15), (4, 6, 5), '-')}"),
    ("account", 2, f"입금 계좌 신한 110-{g.digits(3)}-{g.digits(6)}"),
    ("brn", 1, f"사업자 {g.brn()}"),
    ("passport", 2, f"여권번호: {g.passport()}"),
    ("driver", 2, f"운전면허 {g.driver()}"),
    ("vehicle", 2, f"주차 차량 {g.r.randint(100, 399)}나{g.plain4()}"),
    ("vehicle", 2, f"차량 {g.r.randint(10, 99)}가4567"),
    ("dongho", 2, f"가나아파트 {unit(g)}로 배송"),
    ("name", 1, f"예금주: {FAKE_NAME}"),
    ("key", 2, f"token=ghp_{g.alnum(36)}"),
    ("key", 2, f"KEY=AIza{g.alnum(35)}"),
    ("key", 2, f"aws AKIA{g.alnum(16, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')}"),
    ("key", 2, "pg://app:" + g.alnum(12) + "@db.internal/app"),
    ("jwt", 1, f"eyJ{g.alnum(20)}.eyJ{g.alnum(30)}.{g.alnum(25)}"),
]

CLEAN = [
    "예: 010-1234-5678 처럼 적어 주세요",
    "010-0000-0000",
    "010-XXXX-XXXX · 010-****-1234",
    "900101-1******",
    "2026-10-21 · v3.12.4 · 20261021",
    "가격 1,234,500원",
    "좌표 37.5665, 126.9780",
    "시험 카드 4242 4242 4242 4242",
    f"user@example.com · noreply@github.com · {GIT_ADDRESS}",
    "retina icon@2x.png",
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
    "KexAlgorithms curve25519-sha256@libssh.org",
    "DATABASE_URL=postgresql://user:password@db:5432/app",
    "API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx",
    "성명: 홍길동",
    "고객센터 1588-0000",
    "기업 고객센터 080-" + g.plain4()[:3] + "-" + g.plain4(),
    f"https://images.unsplash.com/photo-{g.timestamp_like_resident()}-{g.hex(12)}?w=800",
    f"/static/photo-{g.timestamp_like_resident()}.jpg",
    f'{{"created_at": {g.timestamp_like_resident()}}}',
    f"주문번호 {g.order_like_resident()}",
    f'{{"order_id": "{g.id_card_like()}"}}',
    f"commit {g.hex(40)}",
    "<lora:name:0.8>",
    "Node.js 24가 2025년 10월에 나옴",
    "mongodb+srv://&lt;username&gt;:&lt;password&gt;" + "@cluster0.mongodb.net/app",
    '"s": 1.5190000000000001, "e": 2.36',
    "서버 203.0.113.77 · DNS 8.8.8.8 · 내부 10.0.0.5",
]


@pytest.mark.parametrize("kind,level,text", FOUND, ids=[f"{k}-{i}" for i, (k, _, _) in enumerate(FOUND)])
def test_found(kind, level, text):
    hits = scan_text(text)
    assert [(f.kind, f.level) for f in hits] == [(kind, level)]


@pytest.mark.parametrize("text", CLEAN, ids=range(len(CLEAN)))
def test_clean(text):
    assert scan_text(text) == []


def test_html_placeholder_and_script():
    phone = g.mobile()
    html = (
        "<html><head><style>.a{color:#010}</style>"
        '<script>var slot = "7564999632"; var mail = "' + g.mail_user() + '@gmail.com";</script></head>'
        f'<body><input type="tel" placeholder="{PLACEHOLDER_PHONE}">'
        f'<p data-x="1">문의 <a href="tel:{phone}">전화</a></p></body></html>'
    )
    kinds = [f.kind for f in scan_text(html, "html")]
    assert kinds == ["email", "mobile"]


def test_csv_header_gives_context():
    rows = f"이름,여권번호\n가나다,{g.passport()}\n"
    assert [f.kind for f in scan_text(rows, "csv")] == ["passport"]
    assert scan_text(rows.replace("여권번호", "코드"), "csv") == []


def test_ignore_marker():
    line = f"{g.mobile()}  # pii-guard-ko: ignore"
    assert scan_text(line) == []


def test_position():
    text = f"첫 줄\n둘째 줄 {g.mobile()}"
    (f,) = scan_text(text)
    assert (f.line, f.col) == (2, 6)
