"""API keys, tokens and credentials."""
import re

PATTERNS = [
    ("sk-ant", r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    ("openai", r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{20,}|(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{48}"),
    ("google", r"AIza[0-9A-Za-z_\-]{35}"),
    ("github", r"gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{60,}"),
    ("gitlab", r"glpat-[A-Za-z0-9_\-]{20}"),
    ("slack", r"xox[abposr]-[A-Za-z0-9-]{10,}"),
    ("slack-webhook", r"hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"),
    ("aws", r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
    ("stripe", r"[sr]k_live_[0-9A-Za-z]{20,}"),
    ("huggingface", r"hf_[A-Za-z0-9]{30,}"),
    ("telegram", r"(?<![0-9])[0-9]{8,10}:AA[A-Za-z0-9_\-]{33}"),
    ("npm", r"npm_[A-Za-z0-9]{36}"),
    ("pypi", r"pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}"),
    ("sendgrid", r"SG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}"),
    ("private-key", r"-----BEGIN (?:(?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED) )?PRIVATE KEY(?: BLOCK)?-----"),
    ("url-password", r"\b[a-z][a-z0-9+.\-]{1,15}://([^\s:/@\"'<>]{1,64}):([^\s:/@\"'<>]{3,64})@[\w.\-]+"),
]
COMPILED = [(name, re.compile(p)) for name, p in PATTERNS]
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")
ASSIGN_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?key|auth[_-]?token|token|passwd|password)"
    r"[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_\-/+=.]{16,})[\"']")

PLACEHOLDER = re.compile(
    r"x{4,}|X{4,}|\*{3,}|your|YOUR|example|EXAMPLE|sample|dummy|DUMMY|placeholder|changeme"
    r"|<|>|&lt;|&gt;|\.\.\.|\u2026|\$\{|%\(|\{\{|abcdef|ABCDEF|0{8,}")
BRACKETS = re.compile(r"&lt;|&gt;|[<>\[\]{}]")
DEMO_USERS = {"user", "username", "admin", "root", "postgres", "test", "name"}
DEMO_PASSWORDS = {"pass", "password", "secret", "changeme", "postgres", "root", "admin", "1234", "****"}


def _placeholder(value):
    return bool(PLACEHOLDER.search(value)) or len(set(value)) < 8


def find_keys(text):
    """Yield (start, end, kind, level, reason) for credentials in text."""
    for name, rx in COMPILED:
        for m in rx.finditer(text):
            value = m.group(0)
            if name == "url-password":
                user, pw = (BRACKETS.sub("", x).lower() for x in m.group(1, 2))
                if user in DEMO_USERS or pw in DEMO_PASSWORDS or PLACEHOLDER.search(m.group(2)):
                    continue
                yield m.start(), m.end(), "key", 2, "주소 속 비밀번호"
                continue
            if name != "private-key" and _placeholder(value):
                continue
            yield m.start(), m.end(), "key", 2, name + " 형식"
    for m in JWT_RE.finditer(text):
        if not _placeholder(m.group(0)):
            yield m.start(), m.end(), "jwt", 1, "JWT 꼴"
    for m in ASSIGN_RE.finditer(text):
        value = m.group(1)
        if _placeholder(value) or value.isdigit() or value.isalpha() or len(set(value)) < 10:
            continue
        yield m.start(1), m.end(1), "key", 1, "키 이름에 붙은 값"
