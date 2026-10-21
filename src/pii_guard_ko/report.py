"""Masking and output formatting."""
import re

LEVEL_NAME = {2: "확실", 1: "의심"}


def mask(value, kind):
    v = value.strip()
    if kind == "email" and "@" in v:
        local, domain = v.split("@", 1)
        return local[:1] + "***@" + domain
    if kind in ("key", "jwt"):
        return f"{v[:4]}…({len(v)}자)"
    if kind in ("rrn", "frn"):
        return v[:2] + re.sub(r"[0-9]", "*", v[2:])
    if kind == "name":
        head, _, name = re.split(r"([:：])", v, maxsplit=1) if re.search("[:：]", v) else ("", "", v)
        name = name.strip()
        return (head + ": " if head else "") + name[:1] + "*" * max(1, len(name) - 1)
    if kind == "address":
        return re.sub(r"[0-9]", "*", v[:6]) + "…"
    if kind in ("dongho", "birth"):
        return re.sub(r"[0-9]", "*", v)
    n = sum(ch.isalnum() for ch in v)
    keep_head, keep_tail = (3, 2) if n >= 10 else (1, 1) if n >= 4 else (0, 0)
    out, k = [], 0
    for ch in v:
        if ch.isalnum():
            out.append(ch if k < keep_head or k >= n - keep_tail else "*")
            k += 1
        else:
            out.append(ch)
    return "".join(out)


def finding_dict(f):
    return {"kind": f.kind, "label": f.label, "level": f.level, "line": f.line, "col": f.col,
            "masked": mask(f.value, f.kind), "reason": f.reason}


def text_line(path, f):
    return f"{path}:{f['line']}:{f['col']}  {LEVEL_NAME[f['level']]}  {f['label']}  {f['masked']}  {f['reason']}"
