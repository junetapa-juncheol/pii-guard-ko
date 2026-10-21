from collections import defaultdict

import pytest

from bench import build
from pii_guard_ko import scan_text
from pii_guard_ko.files import load, walk


@pytest.mark.parametrize("seed", [7, 21, 99])
def test_bench(tmp_path, seed):
    cases = build(tmp_path, seed=seed)
    found = defaultdict(set)
    for path in walk([tmp_path]):
        text, kind, _ = load(path, 1 << 24)
        rel = path.relative_to(tmp_path).as_posix()
        for f in scan_text(text, kind):
            found[rel, f.line].add(f.kind)
            found[rel, None].add(f.kind)
    missed = [c for c in cases if c["kind"] and c["kind"] not in found[c["file"], c["line"]]]
    noisy = [c for c in cases if not c["kind"] and found[c["file"], c["line"]]]
    assert missed == []
    assert noisy == []
