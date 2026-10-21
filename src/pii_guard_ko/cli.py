"""Command line entry point."""
import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .detect import LABELS, scan_text
from .files import IMAGE_EXT, Skip, load, walk
from .report import finding_dict, text_line


def _redacted(text, findings):
    out = text
    for f in sorted(findings, key=lambda f: -f.start):
        out = out[:f.start] + "[" + f.label + "]" + out[f.end:]
    return out


def _image_findings(path):
    from .exif import inspect

    info = inspect(path)
    out = []
    if info["gps"]:
        out.append({"kind": "gps", "label": LABELS["gps"], "level": 2, "line": 0, "col": 0,
                    "masked": "GPS", "reason": "EXIF GPS 있음"})
    if info["owner"]:
        out.append({"kind": "photo_meta", "label": LABELS["photo_meta"], "level": 1, "line": 0, "col": 0,
                    "masked": "메타", "reason": ", ".join(info["owner"])})
    return out


def _targets(paths, exclude):
    for arg in paths:
        if arg == "-":
            yield "-", None
            continue
        p = Path(arg)
        if not p.exists():
            yield p, "없는 경로"
            continue
        base = p if p.is_dir() else p.parent
        for f in walk([p], exclude):
            yield (f, base), None


def scan(args):
    max_bytes = int(args.max_mb * 1024 * 1024)
    exclude = [args.redact] if args.redact else []
    result = {"version": __version__, "scanned": 0, "files": [], "skipped": []}
    for target, problem in _targets(args.paths, exclude):
        if problem:
            result["skipped"].append({"path": str(target), "reason": problem})
            continue
        if target == "-":
            name, text, kind, editable, base, path = "<stdin>", sys.stdin.read(), "text", False, None, None
        else:
            path, base = target
            name = str(path)
            if path.suffix.lower() in IMAGE_EXT:
                if not args.images:
                    continue
                result["scanned"] += 1
                try:
                    hits = _image_findings(path)
                except ImportError:
                    result["skipped"].append({"path": name, "reason": "사진 검사는 Pillow 필요"})
                    continue
                except Exception as e:
                    result["skipped"].append({"path": name, "reason": f"사진 못 엶({type(e).__name__})"})
                    continue
                if hits:
                    result["files"].append({"path": name, "findings": hits})
                continue
            try:
                text, kind, editable = load(path, max_bytes)
            except (Skip, OSError) as e:
                result["skipped"].append({"path": name, "reason": str(e)})
                continue
        result["scanned"] += 1
        findings = scan_text(text, kind)
        if not findings:
            continue
        entry = {"path": name, "findings": [finding_dict(f) for f in findings]}
        if args.redact and editable:
            dest = Path(args.redact) / path.relative_to(base)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(_redacted(text, findings))
            entry["redacted"] = str(dest)
        result["files"].append(entry)

    levels = [f["level"] for e in result["files"] for f in e["findings"]]
    result["summary"] = {
        "sure": levels.count(2),
        "suspect": levels.count(1),
        "files_with_findings": len(result["files"]),
        "by_kind": {},
    }
    for e in result["files"]:
        for f in e["findings"]:
            by = result["summary"]["by_kind"]
            by[f["label"]] = by.get(f["label"], 0) + 1
    result["exit"] = max(levels, default=0)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not args.quiet:
            for e in result["files"]:
                for f in e["findings"]:
                    print(text_line(e["path"], f))
                if e.get("redacted"):
                    print(f"  -> 가린 사본: {e['redacted']}")
            for s in result["skipped"]:
                print(f"건너뜀  {s['path']}  {s['reason']}")
        s = result["summary"]
        head = {0: "깨끗", 1: "의심", 2: "확실"}[result["exit"]]
        print(f"{head} · 검사한 파일 {result['scanned']}개 · 찾은 파일 {s['files_with_findings']}개"
              f" · 확실 {s['sure']} · 의심 {s['suspect']} · 건너뜀 {len(result['skipped'])}")
    return result["exit"]


def strip_gps(args):
    from .exif import strip

    bad = 0
    for arg in args.paths:
        for path in walk([arg]):
            if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            try:
                clean = strip(path.read_bytes(), path.suffix)
            except (ValueError, OSError) as e:
                print(f"실패  {path}  {e}")
                bad += 1
                continue
            dest = path if args.in_place else path.with_name(path.stem + ".clean" + path.suffix)
            dest.write_bytes(clean)
            print(f"지움  {path} -> {dest}")
    return 3 if bad else 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="pii-guard-ko", description="한국어 개인정보·비밀값 검사기")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("scan", help="파일이나 폴더 검사")
    sc.add_argument("paths", nargs="+", help="파일, 폴더, 또는 - (표준 입력)")
    sc.add_argument("--json", action="store_true", help="결과를 JSON으로")
    sc.add_argument("--redact", metavar="DIR", help="찾은 값을 가린 사본을 DIR에 저장")
    sc.add_argument("--images", action="store_true", help="사진 EXIF GPS도 검사 (Pillow 필요)")
    sc.add_argument("--max-mb", type=float, default=20, help="이보다 큰 파일은 건너뜀 (기본 20)")
    sc.add_argument("-q", "--quiet", action="store_true", help="요약 한 줄만")
    sc.set_defaults(func=scan)

    sg = sub.add_parser("strip-gps", help="사진에서 EXIF·XMP 지우기 (방향 정보는 남김)")
    sg.add_argument("paths", nargs="+")
    sg.add_argument("--in-place", action="store_true", help="원본을 덮어씀 (기본은 이름.clean.jpg)")
    sg.set_defaults(func=strip_gps)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"오류: {type(e).__name__}: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
