"""Choose which repository files are worth fetching, and keep file access safe.

DeciTrace never clones a repository. It reads the git tree, drops binaries, generated output,
dependency folders and oversized files, and fetches only the most decision-relevant text files.
"""
import posixpath
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "third_party", "third-party", "dist", "build", "out", "target",
    "__pycache__", ".venv", "venv", "env", "site-packages", ".tox", ".mypy_cache", ".pytest_cache",
    "coverage", "htmlcov", ".next", ".nuxt", "bower_components", "Pods", ".gradle", "bin", "obj",
}
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "Cargo.lock",
    "composer.lock", "Gemfile.lock", "go.sum", "uv.lock",
}
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".icns", ".webp", ".svg", ".pdf", ".zip", ".gz", ".tgz",
    ".bz2", ".xz", ".7z", ".rar", ".tar", ".jar", ".war", ".class", ".so", ".dylib", ".dll", ".exe", ".bin",
    ".o", ".a", ".pyc", ".pyo", ".whl", ".egg", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4",
    ".mov", ".avi", ".wav", ".ogg", ".psd", ".sqlite", ".db", ".pickle", ".pkl", ".npy", ".npz", ".parquet",
    ".h5", ".onnx", ".pt", ".map",
}
SOURCE_EXT = {
    ".py": "python", ".pyi": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".rb": "ruby",
    ".php": "php", ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp",
    ".swift": "swift", ".scala": "scala", ".sql": "sql", ".sh": "shell",
}
DOC_EXT = {".md": "markdown", ".rst": "rst", ".txt": "text", ".adoc": "asciidoc"}
CONFIG_FILES = {
    "pyproject.toml", "setup.py", "setup.cfg", "package.json", "Cargo.toml", "go.mod", "Dockerfile",
    "docker-compose.yml", "Makefile", "tox.ini", "requirements.txt", "tsconfig.json",
}
DECISION_DOC_NAMES = {"readme", "contributing", "architecture", "design", "changelog", "changes", "history", "news"}
DECISION_DIRS = {"adr", "adrs", "decisions", "rfc", "rfcs", "design", "proposals", "peps", "kep", "keps"}


@dataclass(frozen=True)
class TreeFile:
    path: str
    sha: str
    size: int
    language: str
    priority: int


def is_safe_path(path: str) -> bool:
    """Reject anything that could escape the repository or confuse URL building."""
    if not path or len(path) > 1024 or "\x00" in path or "\\" in path:
        return False
    if path.startswith("/") or path.startswith("~"):
        return False
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    return posixpath.normpath(path) == path


def classify(path: str, size: int, max_bytes: int) -> Tuple[int, str, str]:
    """Return (priority, language, skip_reason). Lower priority is fetched first; skip_reason '' means keep."""
    if not is_safe_path(path):
        return 99, "", "unsafe_path"
    parts = path.split("/")
    name = parts[-1]
    lower_dirs = {p.lower() for p in parts[:-1]}
    if lower_dirs & {d.lower() for d in SKIP_DIRS}:
        return 99, "", "dependency_or_generated"
    if name in SKIP_FILES or name.endswith((".min.js", ".min.css")):
        return 99, "", "dependency_or_generated"
    stem, ext = posixpath.splitext(name)
    ext = ext.lower()
    if ext in BINARY_EXT:
        return 99, "", "binary"
    if size > max_bytes:
        return 99, "", "too_large"
    if ext in DOC_EXT or (not ext and stem.upper() in {"README", "CONTRIBUTING", "CHANGELOG"}):
        lang = DOC_EXT.get(ext, "text")
        if stem.lower() in DECISION_DOC_NAMES or lower_dirs & DECISION_DIRS:
            return 0, lang, ""
        return 1, lang, ""
    if name in CONFIG_FILES:
        return 2, "config", ""
    if ext in SOURCE_EXT:
        is_test = any(p in ("test", "tests", "testing", "__tests__", "spec") for p in lower_dirs) or stem.startswith("test_")
        return (4 if is_test else 3), SOURCE_EXT[ext], ""
    return 99, "", "irrelevant_type"


def select_files(entries: Iterable[dict], max_files: int, max_bytes: int) -> Tuple[List[TreeFile], Dict[str, int]]:
    """Pick up to max_files blobs from a git tree listing, most decision-relevant first."""
    keep: List[TreeFile] = []
    skipped: Dict[str, int] = {}
    for e in entries:
        if e.get("type") != "blob":
            continue
        path, size = e.get("path", ""), int(e.get("size") or 0)
        priority, lang, reason = classify(path, size, max_bytes)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        keep.append(TreeFile(path, e["sha"], size, lang, priority))
    keep.sort(key=lambda f: (f.priority, f.path.count("/"), f.path))
    if len(keep) > max_files:
        skipped["over_file_limit"] = len(keep) - max_files
    return keep[:max_files], skipped
