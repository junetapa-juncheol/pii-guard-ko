"""Walk paths and turn files into text."""
import codecs
import os
import re
import zipfile
from html import unescape
from pathlib import Path

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", ".tox",
             ".mypy_cache", ".pytest_cache", ".ruff_cache"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
BINARY_EXT = IMAGE_EXT | {".gif", ".bmp", ".ico", ".heic", ".avif", ".mp3", ".mp4", ".mov", ".wav", ".flac",
                          ".zip", ".gz", ".7z", ".rar", ".tar", ".pdf", ".exe", ".dll", ".so", ".dylib",
                          ".pyc", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".sqlite", ".db", ".bin"}
HTML_EXT = {".html", ".htm", ".xhtml", ".xml", ".svg", ".rss", ".atom"}
OFFICE = {
    ".docx": (("word/document.xml", "word/header", "word/footer", "word/footnotes.xml", "word/comments.xml"),
              ("w:p",), ()),
    ".pptx": (("ppt/slides/slide", "ppt/notesSlides/notesSlide"), ("a:p",), ()),
    ".xlsx": (("xl/sharedStrings.xml", "xl/worksheets/sheet"), ("si", "row"), ("c",)),
    ".hwpx": (("Contents/section",), ("hp:p",), ()),
    ".odt": (("content.xml",), ("text:p", "text:h"), ()),
}


class Skip(Exception):
    pass


def walk(paths, exclude=()):
    """Yield files under the given paths, skipping tool and VCS folders."""
    exclude = {Path(p).resolve() for p in exclude}
    for arg in paths:
        p = Path(arg)
        if p.is_file():
            yield p
            continue
        if not p.is_dir():
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and (Path(root) / d).resolve() not in exclude)
            for name in sorted(files):
                yield Path(root) / name


def decode(data):
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", "replace")


def looks_binary(data):
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return False
    return b"\x00" in data[:8192]


def xml_text(xml, para, cell=()):
    xml = re.sub(r"<w:tab/>", " ", xml)
    xml = re.sub(r"<w:br/>", "\n", xml)
    for tag in para:
        xml = xml.replace(f"</{tag}>", "\n")
    for tag in cell:
        xml = xml.replace(f"</{tag}>", " ")
    return unescape(re.sub(r"<[^>]+>", "", xml))


def office_text(path, spec):
    prefixes, para, cell = spec
    parts = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            if name.endswith(".xml") and name.startswith(prefixes):
                parts.append(xml_text(z.read(name).decode("utf-8", "replace"), para, cell))
    return "\n".join(parts)


def kind_of(path, text):
    ext = path.suffix.lower()
    if ext in HTML_EXT:
        return "html"
    if ext in (".csv", ".tsv"):
        return ext[1:]
    head = text[:1024].lstrip().lower()
    if head.startswith(("<!doctype html", "<html")):
        return "html"
    return "text"


def load(path, max_bytes):
    """Return (text, kind, editable) or raise Skip."""
    ext = path.suffix.lower()
    size = path.stat().st_size
    if size > max_bytes:
        raise Skip(f"{size // (1024 * 1024)}MB 넘음")
    if ext in OFFICE:
        try:
            return office_text(path, OFFICE[ext]), "text", False
        except (zipfile.BadZipFile, KeyError) as e:
            raise Skip(f"문서 못 엶({type(e).__name__})")
    if ext in BINARY_EXT:
        raise Skip("바이너리")
    data = path.read_bytes()
    if looks_binary(data):
        raise Skip("바이너리")
    text = decode(data)
    return text, kind_of(path, text), True
