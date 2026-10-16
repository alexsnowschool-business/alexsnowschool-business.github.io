"""Copy the art-culture-audio venture into dist/ for Cloudflare deploys."""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "art-culture-audio"
DIST = ROOT / "dist"

# Names skipped anywhere inside the venture folder.
IGNORE_NAMES = shutil.ignore_patterns(
    "CLAUDE.md",
    "*.py",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    ".*",
    "__pycache__",
    "node_modules",
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
)

# The site only fetches data/episodes.json and data/completed.json;
# transcript text is embedded in episodes.json.
SKIP = {
    "transcripts",
    "pdfs",
    "src",
    "scripts",
    "test",
    "history",
    "topic_cache",
    "transcribed.json",
    "README.md",
    "QUICKSTART.md",
    "FEATURE_IDEAS.md",
}


def ignore(directory, names):
    return set(IGNORE_NAMES(directory, names)) | SKIP.intersection(names)


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(SRC, DIST, ignore=ignore)

    index = DIST / "index.html"
    html = index.read_text(encoding="utf-8")
    html = html.replace('<a href="../" class="brand">', '<a href="./" class="brand">')
    html = re.sub(r'[ \t]*<a class="header__link" href="\.\./">Portfolio</a>\n', "", html)
    index.write_text(html, encoding="utf-8")

    count = sum(1 for path in DIST.rglob("*") if path.is_file())
    print(f"Built {DIST} with {count} files")


if __name__ == "__main__":
    main()
