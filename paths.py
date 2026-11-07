import posixpath

def safe_path(path: str):
    """Return the full path inside /work, or None if the path is not allowed."""
    if not path or len(path) > 200 or "\x00" in path or path.startswith("/"):
        return None
    clean = posixpath.normpath(path)
    if clean in (".", "..") or clean.startswith("../"):
        return None
    return "/work/" + clean    