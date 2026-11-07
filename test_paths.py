from paths import safe_path

ok = {"note.txt": "/work/note.txt", "sub/a.txt": "/work/sub/a.txt",
      "./x.txt": "/work/x.txt", "a/../b.txt": "/work/b.txt"}
bad = ["", ".", "..", "/etc/passwd", "../x", "a/../../x", "a\x00b", "x" * 300]

for p, want in ok.items():
    assert safe_path(p) == want, p
for p in bad:
    assert safe_path(p) is None, p
print("all path tests passed")