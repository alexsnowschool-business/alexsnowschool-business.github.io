"""Copy the art-culture-audio venture into dist/ for Cloudflare deploys."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "art-culture-audio"
DIST = ROOT / "dist"

# The venture links back to the portfolio hub with "../", which does not exist
# when it is served from the root of its own site.
HUB_URL = "https://alexsnowschool-business.github.io/"

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
    html = html.replace('href="../">Portfolio', f'href="{HUB_URL}">Portfolio')
    index.write_text(html, encoding="utf-8")

    count = sum(1 for path in DIST.rglob("*") if path.is_file())
    print(f"Built {DIST} with {count} files")


if __name__ == "__main__":
    main()
