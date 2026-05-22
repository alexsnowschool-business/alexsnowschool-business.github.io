"""
╔══════════════════════════════════════════════════════════════╗
║                  CLEANUP — Run when done                     ║
║  Removes: converted PNGs, HEIC originals, temp frames, GIFs ║
║  Keeps:   reel.png, reel.mp4, captions.md                   ║
╚══════════════════════════════════════════════════════════════╝
Usage:
    python cleanup.py              # preview what will be deleted
    python cleanup.py --confirm    # actually delete
"""

import os, sys, shutil

# ── CONFIG ────────────────────────────────────────────────────
IMAGES_FOLDER  = "../images"    # where PNGs/HEICs live
OUTPUT_FOLDER  = "../output"    # where reel outputs live
KEEP_FINALS    = True           # always keep reel.png, reel.mp4, captions.md
DELETE_HEICS   = True           # delete original HEIC files after reel is made

# Files/folders to remove
REMOVE_PATTERNS = [
    # Temp frame sequences
    os.path.join(OUTPUT_FOLDER, "_frames"),
    # GIF files (large, replaced by MP4)
    # Converted PNGs in images folder (originals are the HEICs)
]

# ── MAIN ──────────────────────────────────────────────────────
def get_png_files(folder):
    if not os.path.exists(folder):
        return []
    return [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith('.png')
    ]

def get_gif_files(folder):
    if not os.path.exists(folder):
        return []
    return [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith('.gif')
    ]

def get_heic_files(folder):
    if not os.path.exists(folder):
        return []
    return [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith('.heic')
    ]

def human_size(path):
    if os.path.isdir(path):
        total = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, files in os.walk(path)
            for f in files
        )
    else:
        total = os.path.getsize(path)
    if total > 1024**3: return f"{total/1024**3:.1f} GB"
    if total > 1024**2: return f"{total/1024**2:.1f} MB"
    return f"{total/1024:.0f} KB"

def main():
    confirm = "--confirm" in sys.argv

    print("═" * 60)
    print("  REEL CLEANUP")
    print("═" * 60)

    to_delete = []

    # 1. Temp frames folder
    frames_dir = os.path.join(OUTPUT_FOLDER, "_frames")
    if os.path.exists(frames_dir):
        to_delete.append(("dir", frames_dir, "Temp render frames"))

    # 2. GIF files in output
    for gif in get_gif_files(OUTPUT_FOLDER):
        to_delete.append(("file", gif, "GIF slideshow (replaced by MP4)"))

    # 3. Converted PNGs in images folder
    for png in get_png_files(IMAGES_FOLDER):
        stem = png[:-4]  # strip ".png"
        heic_equiv = stem + ".HEIC" if os.path.exists(stem + ".HEIC") else stem + ".heic"
        if os.path.exists(heic_equiv):
            to_delete.append(("file", png, "Converted PNG (HEIC original exists)"))
    for heic in get_heic_files(IMAGES_FOLDER):
        to_delete.append(("file", heic, "Original HEIC"))

    if not to_delete:
        print("\n  ✓ Nothing to clean up — already tidy!")
        return

    print(f"\n  {'ACTION':<8} {'SIZE':<10} {'REASON':<35} PATH")
    print("  " + "-"*56)
    total_freed = 0
    for kind, path, reason in to_delete:
        size_str = human_size(path)
        rel_path = os.path.relpath(path)
        print(f"  {'DEL':<8} {size_str:<10} {reason:<35} {rel_path}")

    print()
    if not confirm:
        print("  ⚠  DRY RUN — nothing deleted yet.")
        print("  Run with --confirm to actually delete:\n")
        print("     python cleanup.py --confirm\n")
    else:
        for kind, path, reason in to_delete:
            try:
                if kind == "dir":
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                print(f"  ✓ Deleted: {os.path.relpath(path)}")
            except Exception as e:
                print(f"  ✗ Failed:  {os.path.relpath(path)} — {e}")

        print("\n  ✓ Cleanup complete.")
        print("  Kept: output/reel.png, output/reel.mp4, output/captions.md")
        print("  ⚠  Original HEIC files deleted — make sure your reel is saved before this step!")

    print("═" * 60)

if __name__ == "__main__":
    main()
