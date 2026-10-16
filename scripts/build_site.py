"""Copy only the publishable site into dist/ for Cloudflare deploys."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

ROOT_FILES = ["index.html"]
VENTURES = [
    "art-archive",
    "art-culture-audio",
    "art-research",
    "hermes-archive",
    "hermes-research",
]

# Names skipped anywhere inside a venture folder.
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

# art-culture-audio: the site only fetches data/episodes.json and
# data/completed.json; transcript text is embedded in episodes.json.
AUDIO_SKIP = {
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
    skipped = set(IGNORE_NAMES(directory, names))
    if Path(directory).name in ("art-culture-audio", "data") and "art-culture-audio" in Path(directory).parts:
        skipped |= AUDIO_SKIP.intersection(names)
    return skipped


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    for name in ROOT_FILES:
        shutil.copy2(ROOT / name, DIST / name)
    for venture in VENTURES:
        shutil.copytree(ROOT / venture, DIST / venture, ignore=ignore)
    count = sum(1 for path in DIST.rglob("*") if path.is_file())
    print(f"Built {DIST} with {count} files")


if __name__ == "__main__":
    main()
