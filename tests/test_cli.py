import json

from bench import Gen, build
from pii_guard_ko.cli import main


def run(capsys, *args):
    code = main(["scan", *map(str, args)])
    return code, capsys.readouterr().out


def test_clean_folder(tmp_path, capsys):
    (tmp_path / "a.txt").write_text("아무것도 없음\n", encoding="utf-8")
    code, out = run(capsys, tmp_path)
    assert code == 0
    assert "검사한 파일 1개" in out


def test_exit_codes(tmp_path, capsys):
    g = Gen(5)
    (tmp_path / "suspect.txt").write_text(f"사무실 {g.landline()}\n", encoding="utf-8")
    assert run(capsys, tmp_path / "suspect.txt")[0] == 1
    (tmp_path / "sure.txt").write_text(f"연락처 {g.mobile()}\n", encoding="utf-8")
    assert run(capsys, tmp_path)[0] == 2


def test_json_has_no_raw_values(tmp_path, capsys):
    bench = tmp_path / "bench"
    build(bench)
    raw = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in bench.iterdir() if p.suffix != ".docx")
    code, out = run(capsys, bench, "--json")
    data = json.loads(out)
    assert code == 2
    assert data["scanned"] == len(list(bench.iterdir()))
    for entry in data["files"]:
        for f in entry["findings"]:
            if f["kind"] in ("dongho", "name", "address"):
                continue
            assert f["masked"] not in raw


def test_redact(tmp_path, capsys):
    g = Gen(6)
    phone = g.mobile()
    src = tmp_path / "src"
    src.mkdir()
    (src / "note.md").write_text(f"줄 하나\r\n연락처 {phone}\r\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    run(capsys, src, "--redact", out_dir)
    data = (out_dir / "note.md").read_bytes().decode("utf-8")
    assert phone not in data
    assert "[휴대폰번호]" in data
    assert data.count("\r\n") == 2


def test_missing_path(tmp_path, capsys):
    code, out = run(capsys, tmp_path / "nope")
    assert code == 0
    assert "없는 경로" in out
