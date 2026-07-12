"""Load per-account configuration from accounts/<slug>.yaml."""

from pathlib import Path
import yaml

BUSINESS_DIR = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = BUSINESS_DIR / "accounts"


def load(slug: str) -> dict:
    path = ACCOUNTS_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No account config found at {path}\n"
            f"Available: {[p.stem for p in ACCOUNTS_DIR.glob('*.yaml')]}"
        )
    with path.open() as f:
        return yaml.safe_load(f)
