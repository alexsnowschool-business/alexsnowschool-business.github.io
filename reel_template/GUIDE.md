# Travel Reel Guide
*iPhone photos → Cinematic reel → Instagram & TikTok*

---

## Overview

| Step | What you do |
|------|-------------|
| Step 1 | Convert HEIC photos to PNG on your Mac |
| Step 2 | Choose your reel style & caption |
| Step 3 | Run `make_reel.py` → `reel.png` + `reel.mp4` |
| Step 4 | Run `make_captions.py` → `captions.md` |
| Step 5 | Post to Instagram & TikTok |
| Step 6 | Run `cleanup.py` → tidy your folder |

---

## Step 1 — Convert HEIC Photos to PNG

Your iPhone saves photos as HEIC files. Claude (Cowork mode) can convert them automatically — just ask! Otherwise you can do it yourself on your Mac:

**Claude (Cowork mode) — automatic, no install needed:**

Just say: *"run the reel script"* or *"convert my HEIC photos"* — Claude will use `libheif` (already available in the sandbox) to convert all HEIC files directly. No action required on your part.

**On your Mac (manual option):**

*Fish shell:*
```fish
for f in /path/to/your/folder/*.HEIC
    sips -s format png $f --out (string replace .HEIC .png $f)
end
```

*Bash or Zsh:*
```bash
for f in /path/to/your/folder/*.HEIC; do
  sips -s format png "$f" --out "${f%.HEIC}.png"
done
```

> 💡 `sips` is built into macOS — no install needed. Replace `/path/to/your/folder/` with your actual folder path.
> To check your shell, run: `echo $SHELL`

---

## Step 2 — Choose Your Style & Caption

Open `make_reel.py` in any text editor and edit the `CONFIG` block at the top.

**Key settings to change every trip:**

| Setting | What it does | Example |
|---------|-------------|---------|
| `caption_tag` | Small label at top of frame | `travel  ·  tokyo  ·  2026` |
| `caption_line1` | Italic whisper (line 1) | `some cities don't` |
| `caption_line2` | Bold hero line (line 2) | `wait for permission` |
| `caption_line3` | Italic close (line 3) | `to change you.` |
| `location_coords` | GPS coordinates | `35°41′N  139°41′E` |
| `location_name` | Location label | `TOKYO  ·  JAPAN` |
| `location_season` | Season / date | `SPRING  ·  2026` |
| `vibe` | Colour palette | `dark_cinematic` |
| `caption_position` | Where caption sits | `upper_third` |

**Available vibes:**

| Vibe | Look | Best for |
|------|------|----------|
| `dark_cinematic` | Deep indigo, cool tones, gold accents | Architecture, winter, night |
| `warm_golden` | Amber, warm shadows, honey highlights | Sunset, golden hour, summer |
| `minimal_clean` | Light, airy, near-white palette | Minimalist, food, flowers |
| `moody_blue` | Deep navy, electric blue, silver | Cityscapes, rain, ocean |
| `museum_calm` | Warm parchment, brass rules, muted tones | Museums, culture, relaxed indoor |

**Caption positions:** `upper_third` · `upper_third_low` · `center` · `lower_third`

| Position | Y offset | Best for |
|----------|----------|----------|
| `upper_third` | Top of frame (y=82) | Most travel shots — clear sky or simple top area |
| `upper_third_low` | Slightly lower (y=200) | Museum/indoor shots where subject starts higher |
| `center` | Middle of frame | Minimalist shots, lots of detail top & bottom |
| `lower_third` | Bottom area | Landscape/horizon shots where sky dominates |

---

## Step 3 — Generate the Reel

Run the shared script, passing your reel folder as the argument. Or just ask Claude — no terminal needed.

```bash
python reel_template/make_reel.py reels/your_reel_name
```

**What it does automatically:**
- Scans `images/` folder for all PNG/JPG files
- Auto-corrects EXIF rotation (so photos aren't sideways)
- Applies your chosen cinematic colour grade to every photo
- Renders the caption block on the opening frame
- Cross-dissolves between photos (default: 3s hold, 1s fade)
- Encodes a full H.264 MP4 at 1080×1920, 30fps

**Output files:**
- `output/reel.png` — static 1080×1920 hero image
- `output/reel.mp4` — full slideshow video (H.264, 30fps)

> 💡 To change video pacing, edit `hold_seconds` and `fade_seconds` in CONFIG.

---

## Step 4 — Generate Captions

Run the shared script, passing your reel folder as the argument. Or just ask Claude.

```bash
python reel_template/make_captions.py reels/your_reel_name
```

**Key settings in `make_captions.py`:**

| Setting | Options |
|---------|---------|
| `topic` | `travel` · `food` · `architecture` · `nature` · `street` · `culture` |
| `location` | City and country name |
| `caption_full` | Full caption text (match your reel) |
| `personal_note` | One sentence in your own voice |
| `engagement_hook` | A question or CTA to drive comments |

**Output:**
- `output/captions.md` — ready-to-copy captions for Instagram and TikTok

> 💡 The script generates 25 hashtags for Instagram and 15 for TikTok, tuned to the topic and location.

---

## Step 5 — Post to Instagram & TikTok

### Instagram

1. Open the Instagram app → tap **+** → select **Reel**
2. Upload `output/reel.mp4`
3. Set `output/reel.png` as the cover thumbnail
4. Paste the Instagram caption from `output/captions.md`
5. Add location tag and publish

> 💡 Best posting times: Tuesday–Friday, 11am–1pm or 7–9pm local time.

### TikTok

1. Open TikTok → tap **+** → **Upload** → select `output/reel.mp4`
2. Paste the TikTok caption from `output/captions.md`
3. Add location, sounds (optional), and publish

> 💡 Best posting times: Tuesday–Thursday 7–9pm, or Saturday morning.

### Format reference

| Platform | Resolution | Codec | Max length | This template |
|----------|-----------|-------|-----------|---------------|
| Instagram Reels | 1080 × 1920 | MP4 H.264 | Up to 90s | ✅ Ready |
| TikTok | 1080 × 1920 | MP4 H.264 | Up to 10m | ✅ Ready |
| Instagram Stories | 1080 × 1920 | MP4 H.264 | Up to 60s | ✅ Ready |
| YouTube Shorts | 1080 × 1920 | MP4 H.264 | Up to 60s | ✅ Ready |

---

## Step 6 — Clean Up

When you're done, run the cleanup script to delete temp files and keep your folder tidy.

```bash
python cleanup.py            # preview what will be deleted
python cleanup.py --confirm  # actually delete
```

**What gets removed:**
- `output/_frames/` — temporary render frames (can be hundreds of MB)
- `*.gif` files — replaced by the MP4
- Converted PNGs — once the HEIC original exists
- Original HEIC files — once `reel.png` and `reel.mp4` are confirmed exported

**What is always kept:**
- `output/reel.png` and `output/reel.mp4` — your final outputs
- `output/captions.md` — your caption text

> ⚠️ **HEIC files will be permanently deleted.** Make sure your reel is saved and backed up before running `--confirm`. If you want to keep your originals, set `DELETE_HEICS = False` in `cleanup.py`.

---

## Folder Structure

```
munich-trip/                      ← your project root
├── reel_template/                ← shared engine — never edit
│   ├── fonts/                    ← all fonts live here
│   ├── make_reel.py              ← single shared script, used by all reels
│   ├── make_captions.py          ← single shared script, used by all reels
│   ├── cleanup.py                ← single shared script, used by all reels
│   └── GUIDE.md                  ← this file
│
└── reels/                        ← one subfolder per reel
    └── your_reel_name/           ← only a config file + images needed
        ├── reel_config.py        ← ✏️ only file you edit — all your settings
        ├── images/               ← drop your PNG photos here
        └── output/               ← reel.png, reel.mp4, captions.md saved here
```

**To start a new reel:**
1. Create a new folder under `reels/` (e.g. `reels/tokyo_shibuya/`)
2. Create `reels/tokyo_shibuya/reel_config.py` — copy from an existing reel and edit the values
3. Drop your PNG photos into `reels/tokyo_shibuya/images/`
4. Ask Claude: *"make the reel for tokyo_shibuya"* — no terminal needed

**Or run manually:**
```bash
python reel_template/make_reel.py     reels/tokyo_shibuya
python reel_template/make_captions.py reels/tokyo_shibuya
```

---

## Tips for Best Results

- **Shoot in good light** — the cinematic grade works best on well-exposed photos.
- **Mix wide & detail shots** — alternate between wide establishing shots and close details for a more engaging slideshow.
- **Keep captions short** — 3 lines max. The hero line (line 2) should be 3–5 words.
- **Portrait photos are ideal** — landscape photos will be cropped to 9:16 from the centre.
- **Match vibe to location** — `dark_cinematic` for European cities & winter · `warm_golden` for Mediterranean & Asia · `moody_blue` for coastal & night.
- **Pick your hero photo** — set `hero_photo` in CONFIG to choose a specific photo for `reel.png`. Otherwise the first photo is used.
- **Reuse the template** — duplicate the entire folder for each new trip. Never overwrite past reels.

---

*Made with Claude · Cowork mode · March 2026*
