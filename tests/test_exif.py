import pytest

from pii_guard_ko import exif

Image = pytest.importorskip("PIL.Image")


def make(path):
    im = Image.new("RGB", (32, 24), (90, 140, 200))
    ex = Image.Exif()
    ex[0x013B] = "Someone"
    ex[0x0112] = 6
    ex.get_ifd(0x8825).update({1: "N", 2: (37.0, 30.0, 0.0), 3: "E", 4: (127.0, 0.0, 0.0)})
    im.save(path, exif=ex.tobytes())


@pytest.mark.parametrize("ext", ["jpg", "png", "webp"])
def test_strip(tmp_path, ext):
    path = tmp_path / f"a.{ext}"
    make(path)
    assert exif.inspect(path)["gps"]
    path.write_bytes(exif.strip(path.read_bytes(), path.suffix))
    info = exif.inspect(path)
    assert not info["gps"] and not info["owner"]
    with Image.open(path) as im:
        im.load()
        if ext == "jpg":
            assert im.getexif().get(0x0112) == 6
