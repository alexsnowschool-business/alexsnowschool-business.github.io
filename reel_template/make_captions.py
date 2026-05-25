"""
╔══════════════════════════════════════════════════════════════╗
║         CAPTION GENERATOR — Instagram & TikTok              ║
║  Usage: python reel_template/make_captions.py reels/<name>   ║
║  Each reel folder needs a reel_config.py with CONFIG dict.   ║
╚══════════════════════════════════════════════════════════════╝
"""

import importlib.util, os, sys
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# CONFIG LOADER — reads reel_config.py from the reel folder
# ══════════════════════════════════════════════════════════════

def load_config(reel_dir):
    config_path = os.path.join(reel_dir, "reel_config.py")
    if not os.path.exists(config_path):
        print(f"  ✗ No reel_config.py found in: {reel_dir}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("reel_config", config_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = dict(mod.CONFIG)
    cfg.setdefault("output_folder", os.path.join(reel_dir, "output"))
    return cfg

# ══════════════════════════════════════════════════════════════
# HASHTAG LIBRARY — edit or extend as needed
# ══════════════════════════════════════════════════════════════

HASHTAG_POOLS = {
    "travel": {
        "ig_core":   ["travelphotography", "travelgram", "wanderlust", "solotravel", "travelblogger", "exploretheworld", "traveleurope"],
        "ig_niche":  ["cinematicphotography", "moodygrams", "darkandmoody", "filmisnotdead", "architecturephotography", "streetphotography"],
        "ig_place":  [],  # filled dynamically from location
        "tt_core":   ["traveltok", "tiktoktravel", "europe", "wanderlust", "travelreels", "solotravel", "europetravel"],
        "tt_viral":  ["fyp", "foryou", "foryoupage"],
    },
    "food": {
        "ig_core":   ["foodphotography", "foodgram", "foodie", "instafood", "foodlover", "gastronomy"],
        "ig_niche":  ["foodstyling", "foodart", "chefsofinstagram", "foodporn", "foodblogger"],
        "ig_place":  [],
        "tt_core":   ["foodtok", "foodtiktok", "foodie", "cooking", "foodlovers", "recipe"],
        "tt_viral":  ["fyp", "foryou", "foryoupage"],
    },
    "architecture": {
        "ig_core":   ["architecture", "architecturephotography", "archidaily", "buildingporn", "architecturelovers"],
        "ig_niche":  ["brutalism", "modernarchitecture", "historicbuildings", "urbanphotography", "streetphotography"],
        "ig_place":  [],
        "tt_core":   ["architecture", "architecturetok", "urbanexploration", "buildings", "citylife"],
        "tt_viral":  ["fyp", "foryou", "foryoupage"],
    },
    "nature": {
        "ig_core":   ["naturephotography", "nature", "landscape", "outdoors", "wilderness", "earthpix"],
        "ig_niche":  ["landscapephotography", "mountainphotography", "natgeo", "wildernessculture", "theoutbound"],
        "ig_place":  [],
        "tt_core":   ["naturetok", "landscape", "outdoors", "wilderness", "mountains", "earthbeauty"],
        "tt_viral":  ["fyp", "foryou", "foryoupage"],
    },
    "street": {
        "ig_core":   ["streetphotography", "streetlife", "urbanphotography", "documentary", "photojournalism"],
        "ig_niche":  ["streetphotographers", "blackandwhite", "candidphotography", "humansofinsta", "everydaylife"],
        "ig_place":  [],
        "tt_core":   ["streetphotography", "urban", "citylife", "documentary", "streetlife"],
        "tt_viral":  ["fyp", "foryou", "foryoupage"],
    },
    "culture": {
        "ig_core":   ["culture", "travel", "history", "heritage", "museum", "art", "artphotography"],
        "ig_niche":  ["culturalheritage", "historicplaces", "aroundtheworld", "travelphotography", "localculture"],
        "ig_place":  [],
        "tt_core":   ["culture", "history", "heritage", "travel", "artsy", "museum"],
        "tt_viral":  ["fyp", "foryou", "foryoupage"],
    },
}

VIBE_TAGS = {
    "cinematic": ["cinematic", "cinematicreels", "cinematicvideo", "reels", "darkcore"],
    "golden":    ["goldenhour", "goldenlight", "warmvibes", "sunsetphotography"],
    "minimal":   ["minimalism", "minimalphotography", "cleanlines", "lessismore"],
    "moody":     ["moodyphotography", "moodygrams", "darkphotography", "brooding"],
    "vibrant":   ["colorful", "vibrant", "colorphotography", "brightcolors"],
}

# ══════════════════════════════════════════════════════════════
# CAPTION TEMPLATES — tone variations
# ══════════════════════════════════════════════════════════════

def make_instagram_caption(cfg, hashtags_ig):
    loc = cfg["location"]
    season = cfg["season"]
    personal = cfg["personal_note"]
    hook = cfg["engagement_hook"]
    full_caption = cfg["caption_full"]

    return f"""{full_caption}

{personal}

{hook}

---
{hashtags_ig}"""

def make_tiktok_caption(cfg, hashtags_tt):
    loc = cfg["location"]
    full_caption = cfg["caption_full"]

    return f"""{full_caption} 🖤

📍 {loc}

{hashtags_tt}"""

def make_linkedin_caption(cfg):
    full_caption = cfg["caption_full"]
    personal = cfg.get("personal_note", "")
    hook = cfg.get("engagement_hook", "")

    # Strip any hashtags already embedded in the hook
    hook_clean = " ".join(w for w in hook.split() if not w.startswith("#")).strip()

    parts = [full_caption]
    if personal:
        parts.append(personal)
    if hook_clean:
        parts.append(hook_clean)
    parts.append("#thehammerprice #artmarket #auctionresults #artcollecting #contemporaryart")
    return "\n\n".join(parts)

def make_caption_variations(cfg):
    loc  = cfg["location"].split(",")[0].lower()
    hero = cfg["caption_hero"].lower()
    return [
        f"📍 {loc}. {cfg['caption_full']}",
        f"what's the place that changed you without warning? for me it was {loc}. 🏔️",
        f"{loc} at its most quiet. {cfg['caption_full']}",
    ]

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python reel_template/make_captions.py reels/<name>")
        sys.exit(1)
    reel_dir = os.path.abspath(sys.argv[1])
    cfg    = load_config(reel_dir)
    topic  = cfg["topic"]
    vibe   = cfg["vibe"]
    loc    = cfg["location"]
    os.makedirs(cfg["output_folder"], exist_ok=True)

    pool = HASHTAG_POOLS.get(topic, HASHTAG_POOLS["travel"])
    vibe_tags = VIBE_TAGS.get(vibe, [])

    # Build location-based tags
    loc_parts = [w.lower().replace(",","").replace(" ","") for w in loc.split()]
    location_tags = loc_parts + [loc.lower().replace(", ","").replace(" ","")]

    # Instagram hashtags (25 max for best reach)
    ig_tags = (
        pool["ig_core"] +
        pool["ig_niche"][:4] +
        vibe_tags[:3] +
        location_tags[:4] +
        ["reels", "explore"]
    )[:25]
    ig_hashtags = " ".join(f"#{t}" for t in ig_tags)

    # TikTok hashtags (keep tighter — 10-15 is sweet spot)
    tt_tags = (
        pool["tt_core"][:6] +
        vibe_tags[:2] +
        location_tags[:2] +
        pool["tt_viral"]
    )[:15]
    tt_hashtags = " ".join(f"#{t}" for t in tt_tags)

    ig_caption = make_instagram_caption(cfg, ig_hashtags)
    tt_caption = make_tiktok_caption(cfg, tt_hashtags)
    ln_caption = make_linkedin_caption(cfg)
    variations = make_caption_variations(cfg)

    # Best posting times
    ig_times = "Tue–Fri, 11am–1pm or 7–9pm (your local time)"
    tt_times  = "Tue–Thu 7–9pm or Sat morning (your local time)"

    out_path = os.path.join(cfg["output_folder"], "captions.md")
    with open(out_path, "w") as f:
        f.write(f"# Social Media Captions\n")
        f.write(f"*{cfg['location']} · {cfg['season']} · {cfg['topic'].capitalize()}*\n\n")
        f.write("---\n\n")

        f.write("## 📸 Instagram\n\n")
        f.write(f"**Best time to post:** {ig_times}\n")
        f.write(f"**Cover image:** `output/reel.png`\n\n")
        f.write("### Caption\n\n")
        f.write("```\n")
        f.write(ig_caption)
        f.write("\n```\n\n")

        f.write("---\n\n")
        f.write("## 🎵 TikTok\n\n")
        f.write(f"**Best time to post:** {tt_times}\n")
        f.write(f"**Video:** `output/reel.mp4`\n\n")
        f.write("### Caption\n\n")
        f.write("```\n")
        f.write(tt_caption)
        f.write("\n```\n\n")

        f.write("---\n\n")
        f.write("## 💼 LinkedIn\n\n")
        f.write(f"**Best time to post:** Tue–Thu, 8–10am or 12–1pm (your local time)\n")
        f.write(f"**Video:** `output/reel.mp4`\n\n")
        f.write("### Caption\n\n")
        f.write("```\n")
        f.write(ln_caption)
        f.write("\n```\n\n")

        f.write("---\n\n")
        f.write("## ✏️ Caption Variations\n\n")
        for i, v in enumerate(variations, 1):
            f.write(f"{i}. *{v}*\n")

        f.write(f"\n---\n*Generated {datetime.now().strftime('%B %d, %Y')}*\n")

    print(f"✓ Captions saved to: {out_path}")
    print("\n── INSTAGRAM ──────────────────────────────")
    print(ig_caption[:300] + "...")
    print("\n── TIKTOK ─────────────────────────────────")
    print(tt_caption)

if __name__ == "__main__":
    main()
