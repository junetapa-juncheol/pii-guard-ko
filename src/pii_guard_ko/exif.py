"""Find and remove location and owner data in photos.

Reading tags needs Pillow. Removing them is plain byte surgery and keeps the
image data untouched (JPEG, PNG, WebP).
"""
import struct

OWNER_TAGS = {0x013B: "Artist", 0x9C9D: "XPAuthor", 0xA430: "CameraOwnerName",
              0xA431: "BodySerialNumber", 0xA435: "LensSerialNumber"}


def _filled(v):
    if v is None:
        return False
    if isinstance(v, bytes):
        return bool(v.strip(b"\x00 "))
    return bool(str(v).strip())


def inspect(path):
    """Return {'gps': bool, 'owner': [tag names]}."""
    from PIL import Image

    with Image.open(path) as im:
        ex = im.getexif()
        gps = ex.get_ifd(0x8825) if ex else {}
        sub = ex.get_ifd(0x8769) if ex else {}
        found_gps = bool(gps) and (2 in gps or 4 in gps)
        owner = [n for tag, n in OWNER_TAGS.items() if _filled(ex.get(tag)) or _filled(sub.get(tag))]
        xmp = im.info.get("xmp") or im.info.get("XML:com.adobe.xmp") or b""
    if isinstance(xmp, str):
        xmp = xmp.encode("utf-8", "ignore")
    if b"GPSLatitude" in xmp or b"GPSLongitude" in xmp:
        found_gps = True
    if b"dc:creator" in xmp:
        owner.append("XMP creator")
    return {"gps": found_gps, "owner": owner}


def _orientation(payload):
    tiff = payload[6:]
    if len(tiff) < 8 or tiff[:2] not in (b"II", b"MM"):
        return 1
    bo = "<" if tiff[:2] == b"II" else ">"
    off = struct.unpack(bo + "I", tiff[4:8])[0]
    try:
        count = struct.unpack(bo + "H", tiff[off:off + 2])[0]
        for i in range(count):
            e = off + 2 + i * 12
            tag = struct.unpack(bo + "H", tiff[e:e + 2])[0]
            if tag == 0x0112:
                return struct.unpack(bo + "H", tiff[e + 8:e + 10])[0]
    except struct.error:
        pass
    return 1


def _orientation_segment(value):
    tiff = b"II*\x00" + struct.pack("<IH", 8, 1) + struct.pack("<HHIHH", 0x0112, 3, 1, value, 0) + b"\x00" * 4
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def strip_jpeg(data):
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    head, body, i = [], [], 2
    orientation = 1
    while i < len(data):
        if data[i] != 0xFF:
            raise ValueError("broken JPEG")
        marker = data[i + 1]
        if marker in (0xD9, 0xDA):
            body.append(data[i:])
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            body.append(data[i:i + 2])
            i += 2
            continue
        size = struct.unpack(">H", data[i + 2:i + 4])[0]
        seg = data[i:i + 2 + size]
        if marker == 0xE1:
            if seg[4:10] == b"Exif\x00\x00" and orientation == 1:
                orientation = _orientation(seg[4:])
        elif marker in (0xED, 0xFE):
            pass
        elif marker == 0xE0 and not body:
            head.append(seg)
        else:
            body.append(seg)
        i += 2 + size
    keep = _orientation_segment(orientation) if orientation != 1 else b""
    return b"\xff\xd8" + b"".join(head) + keep + b"".join(body)


def strip_png(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    out, i = [data[:8]], 8
    while i < len(data):
        size = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        if kind not in (b"eXIf", b"tEXt", b"zTXt", b"iTXt"):
            out.append(data[i:i + 12 + size])
        i += 12 + size
        if kind == b"IEND":
            break
    return b"".join(out)


def strip_webp(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a WebP")
    body, i = bytearray(), 12
    while i + 8 <= len(data):
        kind = data[i:i + 4]
        size = struct.unpack("<I", data[i + 4:i + 8])[0]
        chunk = bytearray(data[i:i + 8 + size + (size & 1)])
        if kind == b"VP8X":
            chunk[8] &= ~0x0C & 0xFF
        if kind not in (b"EXIF", b"XMP "):
            body += chunk
        i += 8 + size + (size & 1)
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + bytes(body)


def strip(data, suffix):
    suffix = suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return strip_jpeg(data)
    if suffix == ".png":
        return strip_png(data)
    if suffix == ".webp":
        return strip_webp(data)
    raise ValueError(f"{suffix} is not supported")
