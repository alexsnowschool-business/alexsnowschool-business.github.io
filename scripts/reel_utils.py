"""
Shared utilities for reel generators (auto_reel.py, hermes_reel.py, etc.).

Covers: image download (Playwright + httpx fallback), TTS synthesis
(ElevenLabs + Edge TTS fallback), word-level caption helpers, SRT writing,
ffmpeg caption burning, and common string utilities.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import unicodedata
from pathlib import Path

import httpx


# ── String utilities ──────────────────────────────────────────────────────────

def esc(s: str) -> str:
    """Escape a value for safe embedding inside a double-quoted Python string literal."""
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def make_slug(text: str, max_len: int = 25) -> str:
    """Lowercase filesystem-safe slug: strip accents, collapse spaces to hyphens."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:max_len].rstrip("-")


# ── Image downloading ─────────────────────────────────────────────────────────

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def download_images_playwright(
    urls: list[str],
    dest_dir: Path,
    max_images: int = 8,
    user_agent: str = _DEFAULT_UA,
    prime_url: str | None = None,
) -> list[Path]:
    """
    Download images via a real Chromium browser to bypass CDN bot-protection.

    If *prime_url* is given, the browser navigates there first to acquire
    session cookies / Cloudflare clearance, then navigates directly to each
    image URL (full page.goto — harder to fingerprint than context.request).
    Without *prime_url*, uses the lighter context.request.get with per-image
    Referer headers (works for most auction-house CDNs).
    """
    import asyncio
    from urllib.parse import urlparse
    from playwright.async_api import async_playwright

    _CT_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

    async def _fetch_all() -> list[Path]:
        saved: list[Path] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent=user_agent,
                locale="en-US",
                extra_http_headers={
                    "Accept":          "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                },
            )

            if prime_url:
                # CF-bypass path: prime with a homepage visit so session cookies
                # and TLS fingerprints look legitimate, then navigate to each image.
                page = await context.new_page()
                await page.goto(prime_url, wait_until="domcontentloaded", timeout=30_000)

                for i, url in enumerate(urls[:max_images]):
                    try:
                        resp = await page.goto(url, wait_until="load", timeout=20_000)
                        if not resp or not resp.ok:
                            status = resp.status if resp else "no response"
                            print(f"  ✗ {url[:70]}... — HTTP {status}")
                            continue
                        ct  = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                        ext = _CT_EXT.get(ct) or (
                            ".jpg" if ("jpg" in url.lower() or "jpeg" in url.lower()) else ".png"
                        )
                        fname = dest_dir / f"src_{i + 1:02d}{ext}"
                        fname.write_bytes(await resp.body())
                        print(f"  ✓ {fname.name}")
                        saved.append(fname)
                    except Exception as e:
                        print(f"  ✗ {url[:70]}... — {e}")

            else:
                # Standard path: context.request.get with per-image Referer.
                for i, url in enumerate(urls[:max_images]):
                    parsed  = urlparse(url)
                    referer = f"{parsed.scheme}://{parsed.netloc}/"
                    for attempt in range(3):
                        try:
                            resp = await context.request.get(
                                url,
                                headers={"Referer": referer},
                                timeout=30_000,
                            )
                            if not resp.ok:
                                print(f"  ✗ {url[:70]}... — HTTP {resp.status}")
                                break
                            body = await resp.body()
                            ct   = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                            ext  = _CT_EXT.get(ct) or (
                                ".jpg" if ("jpg" in url.lower() or "jpeg" in url.lower()) else ".png"
                            )
                            fname = dest_dir / f"src_{i + 1:02d}{ext}"
                            fname.write_bytes(body)
                            print(f"  ✓ {fname.name}")
                            saved.append(fname)
                            break
                        except Exception as e:
                            if attempt == 2:
                                print(f"  ✗ {url[:70]}... — {e}")

            await browser.close()
        return saved

    return asyncio.run(_fetch_all())


def download_images(
    urls: list[str],
    dest_dir: Path,
    max_images: int = 8,
    headers: dict | None = None,
    prime_url: str | None = None,
) -> list[Path]:
    """
    Download images, trying Playwright first; falls back to plain httpx.

    *prime_url* is forwarded to the Playwright downloader for CF-bypass priming.
    *headers* is used only in the httpx fallback.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    if importlib.util.find_spec("playwright") is not None:
        return download_images_playwright(
            urls, dest_dir, max_images, prime_url=prime_url
        )

    _CT_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    _h = headers or {"User-Agent": _DEFAULT_UA}
    saved: list[Path] = []
    with httpx.Client(headers=_h, follow_redirects=True, timeout=20) as client:
        for i, url in enumerate(urls[:max_images]):
            try:
                r = client.get(url)
                r.raise_for_status()
                ct  = r.headers.get("content-type", "").split(";")[0].strip().lower()
                ext = _CT_EXT.get(ct) or (
                    ".jpg" if ("jpg" in url.lower() or "jpeg" in url.lower()) else ".png"
                )
                fname = dest_dir / f"src_{i + 1:02d}{ext}"
                fname.write_bytes(r.content)
                print(f"  ✓ {fname.name}")
                saved.append(fname)
            except Exception as e:
                print(f"  ✗ {url[:70]}... — {e}")
    return saved


# ── Audio ─────────────────────────────────────────────────────────────────────

def audio_duration(path: Path) -> float:
    """Return audio file duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def synthesise_via_edge_tts(
    text: str,
    output_path: Path,
    voice: str = "en-US-AriaNeural",
) -> bool:
    """Free fallback TTS via Microsoft Edge TTS (no API key required)."""
    try:
        import asyncio
        import edge_tts

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))

        asyncio.run(_run())
        print(f"  ✓ Edge TTS (voice={voice}) → {output_path.name}")
        return True
    except ImportError:
        print("  ✗ edge-tts not installed (pip install edge-tts)")
        return False
    except Exception as e:
        print(f"  ✗ Edge TTS error: {e}")
        return False


def synthesise_voiceover(
    text: str,
    output_path: Path,
    elevenlabs_key: str | None,
    voice_id: str,
    model_id: str = "eleven_turbo_v2_5",
    edge_voice: str = "en-US-AriaNeural",
    stability: float = 0.45,
    similarity_boost: float = 0.80,
    style: float = 0.2,
) -> tuple[bool, list[dict]]:
    """
    Synthesise text to MP3.  Tries ElevenLabs first; falls back to Edge TTS.

    Returns (success, word_timestamps).  Word timestamps are populated only
    when ElevenLabs is used (provides character-level alignment).
    """
    if elevenlabs_key and voice_id:
        try:
            import base64
            from elevenlabs import VoiceSettings
            from elevenlabs.client import ElevenLabs

            client   = ElevenLabs(api_key=elevenlabs_key)
            response = client.text_to_speech.convert_with_timestamps(
                voice_id=voice_id,
                text=text,
                model_id=model_id,
                output_format="mp3_44100_128",
                voice_settings=VoiceSettings(
                    stability=stability,
                    similarity_boost=similarity_boost,
                    style=style,
                ),
            )
            output_path.write_bytes(base64.b64decode(response.audio_base_64))
            print(f"  ✓ ElevenLabs TTS (voice={voice_id}) → {output_path.name}")
            raw       = response.alignment
            alignment = raw.__dict__ if hasattr(raw, "__dict__") else (raw or {})
            words     = alignment_to_words(alignment)
            return True, words
        except Exception as e:
            print(f"  ✗ ElevenLabs error: {e} — falling back to Edge TTS")

    print("  ▸ Using Edge TTS fallback")
    ok = synthesise_via_edge_tts(text, output_path, voice=edge_voice)
    return ok, []


# ── Word / caption helpers ────────────────────────────────────────────────────

def alignment_to_words(alignment: dict) -> list[dict]:
    """Convert ElevenLabs character-level alignment into word-level timestamps."""
    chars  = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends   = alignment.get("character_end_times_seconds", [])

    words: list[dict] = []
    buf: list[str]    = []
    buf_start = buf_end = None

    for ch, s, e in zip(chars, starts, ends):
        if ch in (" ", "\n", "\t"):
            if buf:
                words.append({"word": "".join(buf), "start": buf_start, "end": buf_end})
                buf, buf_start, buf_end = [], None, None
        else:
            if buf_start is None:
                buf_start = s
            buf_end = e
            buf.append(ch)

    if buf:
        words.append({"word": "".join(buf), "start": buf_start, "end": buf_end})
    return words


def evenly_spaced_words(text: str, duration: float) -> list[dict]:
    """Distribute words evenly across the audio duration (fallback when no timestamps)."""
    tokens = text.split()
    if not tokens or duration <= 0:
        return []
    step = duration / len(tokens)
    return [{"word": w, "start": i * step, "end": (i + 1) * step}
            for i, w in enumerate(tokens)]


def normalise_word_timings(words: list[dict]) -> list[dict]:
    """Normalise word timing dicts to always use {word, start, end}."""
    result = []
    for w in words:
        word  = w.get("word") or w.get("text") or w.get("char") or ""
        start = float(
            w.get("start") or w.get("start_time") or
            w.get("startTime") or w.get("start_seconds") or 0.0
        )
        end = float(
            w.get("end") or w.get("end_time") or
            w.get("endTime") or w.get("end_seconds") or start
        )
        result.append({"word": word, "start": start, "end": end})
    return result


def split_sentences(words: list[dict]) -> list[list[dict]]:
    """Group word dicts into sentence-level chunks by terminal punctuation."""
    sentences, current = [], []
    for w in words:
        current.append(w)
        if re.search(r'[.?!]\s*$', w["word"]):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)
    return sentences


def words_to_captions(
    words: list[dict],
    words_per_cue: int = 6,
    min_duration: float = 0.6,
    tail: float = 0.1,
) -> list[dict]:
    """Group word timestamps into caption cues (for overlay or narration_captions)."""
    captions = []
    for i in range(0, len(words), words_per_cue):
        chunk = words[i : i + words_per_cue]
        start = chunk[0]["start"]
        end   = max(chunk[-1]["end"] + tail, start + min_duration)
        captions.append({
            "start": start,
            "end":   end,
            "text":  " ".join(w["word"] for w in chunk).lower(),
        })
    return captions


def _srt_ts(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(
    words: list[dict],
    path: Path,
    words_per_cue: int = 6,
    min_duration: float = 0.6,
    tail: float = 0.1,
) -> None:
    """Write word-grouped captions as an SRT subtitle file."""
    groups = [words[i : i + words_per_cue] for i in range(0, len(words), words_per_cue)]
    lines: list[str] = []
    for idx, chunk in enumerate(groups, start=1):
        start = chunk[0]["start"]
        end   = max(chunk[-1]["end"] + tail, start + min_duration)
        text  = " ".join(w["word"] for w in chunk).lower()
        lines += [str(idx), f"{_srt_ts(start)} --> {_srt_ts(end)}", text, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ Captions SRT: {path.name}  ({len(groups)} cues)")


# ── ffmpeg / video ────────────────────────────────────────────────────────────

def ffmpeg_has_libass() -> bool:
    """Return True if the local ffmpeg was compiled with libass (subtitles filter)."""
    try:
        r = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
        return "subtitles" in r.stdout or "subtitles" in r.stderr
    except FileNotFoundError:
        return False


def burn_captions(video_path: Path, srt_path: Path) -> Path | None:
    """Burn SRT subtitles into a video with ffmpeg. Returns the output path or None."""
    if not ffmpeg_has_libass():
        print("  ✗ ffmpeg compiled without libass — subtitles filter unavailable.")
        print("    Fix: brew uninstall ffmpeg && brew install ffmpeg")
        return None

    out   = video_path.with_stem(video_path.stem + "_captioned")
    style = (
        "FontName=Arial,FontSize=55,Bold=1,Alignment=2,WrapStyle=2,"
        "MarginL=40,MarginR=40,MarginV=60,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1"
    )
    srt_abs = str(srt_path.resolve()).replace("\\", "\\\\").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles='{srt_abs}':force_style='{style}'",
        "-c:a", "copy",
        str(out),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✓ Captioned video: {out.name}")
            return out
        print(f"  ✗ ffmpeg subtitles error: {result.stderr[-400:]}")
        return None
    except FileNotFoundError:
        print("  ✗ ffmpeg not found — install it to burn captions into the video")
        return None
