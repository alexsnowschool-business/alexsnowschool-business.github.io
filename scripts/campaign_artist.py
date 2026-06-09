#!/usr/bin/env python3
"""
Print the campaign artist for today based on a continuous day-offset rotation.

Usage:
    python scripts/campaign_artist.py              # today
    python scripts/campaign_artist.py 2026-07-15   # specific date

The rotation cycles indefinitely. Each artist holds for DAYS_PER_ARTIST days.
Edit ROTATION to add/remove artists. Order = posting sequence.
"""

import sys
from datetime import date

# ── Rotation ──────────────────────────────────────────────────────────────────
# Data-driven: only artists with ≥5 lots in art.db, ordered by social reach.
# DB lot counts shown as comments so it's easy to rebalance.

DAYS_PER_ARTIST = 2

ROTATION = [
    # Street / pop — widest non-art audience, opens the cycle with energy
    "Basquiat",          #  7 lots  avg +52%   max $13.8M
    "Warhol",            # 24 lots  avg +207%  max $10M
    "Haring",            #  9 lots  avg +193%  max $4.2M
    "Lichtenstein",      # 47 lots  avg +107%  max $4.5M   ← deepest pop art pool

    # Visual-first — image carries the post without the name doing the work
    "Kusama",            # 24 lots  avg +84%   max $54M
    "Murakami",          #  8 lots  avg +21%   max $19M
    "Nara",              # 12 lots  avg +61%   max $86M    ← biggest hammer in DB
    "Miró",              # 20 lots  avg +270%  max $4M

    # Sculpture — underused format, distinctive visuals
    "Calder",            # 22 lots  avg +89%   max $12.4M
    "Rodin",             # 11 lots  avg +107%  max $2.8M

    # Collector / institutional — serious money, auction drama
    "Picasso",           # 42 lots  avg +68%   max $12.8M
    "Matisse",           # 14 lots  avg +137%  max $1.4M
    "Mitchell",          # 18 lots  avg +65%   max $20.8M  ← surprise hammer
    "Hockney",           # 11 lots  avg +62%   max $7.5M

    # Controversial / reaction-bait
    "Hirst",             #  8 lots  avg +78%   max $1.8M
    "Condo",             # 10 lots  avg +52%   max $19M
    "Magritte",          #  7 lots  avg +33%   max $16M

    # Hidden story — less famous name, shocking result (comment magnet)
    "Carrington",        #  5 lots  avg +164%  max $25M    ← +108% on a $12M est
    "Chagall",           # 58 lots  avg +636%  max $4.5M   ← biggest avg overshoot in DB
    "Ruscha",            # 11 lots  avg +94%   max $7.5M

    # Close with the heaviest names
    "Basquiat",          # second pass mid-cycle — high performer worth repeating
    "Kusama",            # second pass — 3 of top 10 by price
    "Warhol",            # second pass — deepest social recognition
    "Picasso",           # always close with Picasso
]

# Anchor date: day 0 of the rotation.
_EPOCH = date(2026, 7, 1)


def artist_for_date(d: date) -> str:
    day_offset = (d - _EPOCH).days
    cycle_len  = len(ROTATION) * DAYS_PER_ARTIST
    slot = (day_offset % cycle_len + cycle_len) % cycle_len
    return ROTATION[slot // DAYS_PER_ARTIST]


if __name__ == "__main__":
    ref = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    print(artist_for_date(ref))
