# Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Setup (One-time)

```bash
# Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies
cd /home/wut/playground/reith-lecture
uv sync

# Configure your Google AI API key
cp .env.example .env
# Edit .env and add your GOOGLE_AI_API_KEY
```

### 2. Run the App

```bash
uv run python app.py
```

Open browser to: http://localhost:7860

### 3. Use the Interface

**Tab 1 - Download:**
- Enter RSS feed: `https://podcasts.files.bbci.co.uk/p00fzl9g.rss`
- Set limit: `3`
- Click "Download from RSS"

**Tab 2 - Transcribe:**
- Refresh audio list
- Select a downloaded file
- Choose model: `base` (recommended)
- Click "Transcribe Selected File"

**Tab 3 - Chat:**
- Click "Load Transcripts to Vector Store"
- Ask: "What are the main themes discussed?"
- Get AI-powered responses with source citations!

## 📚 Popular BBC Feeds

- **Reith Lectures**: `https://podcasts.files.bbci.co.uk/p00fzl9g.rss`
- **In Our Time**: `https://podcasts.files.bbci.co.uk/p01f0vzr.rss`
- **The Documentary**: `https://podcasts.files.bbci.co.uk/p02nq0lx.rss`
- **Analysis**: `https://podcasts.files.bbci.co.uk/b006r4vz.rss`

## 💡 Tips

- Start with `base` Whisper model (good balance of speed/accuracy)
- Transcription is FREE and runs locally (no API costs)
- Load transcripts to vector store once per session
- All data stored locally in `downloads/`, `transcripts/`, and `data/`

## 🔧 Troubleshooting

**Chat not working?**
- Make sure you set `GOOGLE_AI_API_KEY` in `.env`
- Get free key at: https://makersuite.google.com/app/apikey

**Need FFmpeg?**
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

**Verify installation:**
```bash
uv run python test_installation.py
```
