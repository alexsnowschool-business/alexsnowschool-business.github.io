---
title: Bbc Audio Rag Reith Lecture
emoji: 🌍
colorFrom: gray
colorTo: blue
sdk: gradio
sdk_version: 6.0.0
app_file: app.py
pinned: false
license: mit
short_description: A free, open-source system for downloading BBC audio program
---

# 🎙️ BBC Audio Transcript

> Download BBC podcasts and transcribe with Whisper

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![uv](https://img.shields.io/badge/managed%20by-uv-blue)](https://docs.astral.sh/uv/)

A complete end-to-end system for downloading and transcribing BBC audio content. Built entirely with **free and open-source tools** — no paid APIs required for transcription!

### ✨ What Makes This Special

- 🆓 **100% Free Transcription**: Uses OpenAI Whisper locally (no API costs)
- 🎨 **Beautiful UI**: Intuitive Gradio web interface
- 📦 **Modern Stack**: Managed with `uv` for fast, reliable dependency management
- 🚀 **Deploy Ready**: One-click deployment to HuggingFace Spaces

## 🎯 Features

### 📥 Audio Download
- Download BBC podcasts via RSS feeds (recommended)
- Support for get_iplayer for BBC iPlayer content
- Batch download multiple episodes
- Popular BBC podcast feeds included

### 🎯 Local Transcription
- Powered by OpenAI Whisper (runs on your machine)
- Multiple model sizes: `tiny`, `base`, `small`, `medium`, `large`
- No API costs or usage limits
- Batch transcription support
- Automatic audio preprocessing

### Web Interface
- Clean, intuitive Gradio interface
- Tabs for Download, Transcribe, Read & Listen, and History
- Real-time progress updates
- File management built-in

## Tech Stack

### Core Technologies
- **[Python 3.9+](https://www.python.org/)** - Programming language
- **[uv](https://docs.astral.sh/uv/)** - Fast Python package manager and project manager
- **[Gradio](https://gradio.app/)** - Web UI framework

### AI & ML
- **[OpenAI Whisper](https://github.com/openai/whisper)** - Speech-to-text transcription (local, free)
- **[Google Gemini](https://ai.google.dev/)** - Powers topic categorization (free tier available)

### Audio Processing
- **[FFmpeg](https://ffmpeg.org/)** - Audio/video processing
- **[pydub](https://github.com/jiaaro/pydub)** - Audio manipulation

### Data & Utilities
- **[feedparser](https://feedparser.readthedocs.io/)** - RSS feed parsing
- **[requests](https://requests.readthedocs.io/)** - HTTP library
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** - Environment variable management

## 📋 Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/) (modern Python package manager)
- FFmpeg (for audio processing)
- Optional: Google AI API key (free tier) for topic categorization
- Optional: get_iplayer for BBC iPlayer downloads

## ⚡ Quick Start

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone the repository
git clone <your-repo-url>
cd bbc-audio-rag

# 3. Install dependencies
uv sync

# 4. (Optional) Set up your Google AI API key for topic categorization
cp .env.example .env
# Edit .env and add your GOOGLE_AI_API_KEY

# 5. Run the app
uv run python app.py
```

Then open your browser to `http://localhost:7860` and start downloading and transcribing! 🎉

## 🚀 Detailed Installation

### 1. Install uv (if not already installed)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

### 2. Clone and Setup

```bash
cd /home/wut/playground/reith-lecture

# Create virtual environment and install all dependencies
uv sync
```

This will:
- Create a `.venv` virtual environment
- Install all dependencies from `pyproject.toml`
- Set up the project in editable mode

### 3. Install FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html

### 3. Install get_iplayer (Optional)

```bash
# Ubuntu/Debian
sudo apt install get-iplayer

# macOS
brew install get_iplayer

# Or install from: https://github.com/get-iplayer/get_iplayer
```

### 4. Configure API Keys (Optional)

Topic categorization uses Google AI. Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and add your Google AI API key:

```
GOOGLE_AI_API_KEY=your_api_key_here
```

Get a free Google AI API key at: https://makersuite.google.com/app/apikey

## 💻 Usage

### Run the Gradio App

```bash
uv run python app.py
```

Then open your browser to `http://localhost:7860`

### Command Line Usage

**Download audio from RSS feed:**
```bash
uv run python -c "from src.scraper.rss_scraper import RSScraper; scraper = RSScraper(); scraper.download_episodes('https://podcasts.files.bbci.co.uk/p00fzl9g.rss', limit=5)"
```

**Transcribe audio:**
```bash
uv run python -c "from src.transcription.transcriber import WhisperTranscriber; transcriber = WhisperTranscriber(model_size='base'); transcript = transcriber.transcribe_and_save('downloads/episode.mp3'); print(transcript)"
```

## 📁 Project Structure

```
reith-lecture/
├── app.py                      # Main Gradio application
├── config.py                   # Configuration management
├── requirements.txt            # Python dependencies
├── .env.example               # Environment variables template
├── README.md                  # This file
├── src/
│   ├── scraper/
│   │   ├── bbc_scraper.py    # BBC website scraper
│   │   ├── get_iplayer_wrapper.py  # get_iplayer wrapper
│   │   └── rss_scraper.py    # RSS feed parser
│   ├── transcription/
│   │   ├── transcriber.py    # Whisper transcription (FREE)
│   │   └── audio_processor.py # Audio utilities
│   └── utils/
│       ├── logger.py          # Logging utilities
│       └── file_manager.py    # File management
├── downloads/                  # Downloaded audio files
├── transcripts/               # Generated transcripts
└── tests/                     # Unit tests
```

## 🌐 Deploy to HuggingFace Spaces

1. Create a new Space at https://huggingface.co/spaces
2. Choose "Gradio" as the SDK
3. Upload all files from this project
4. (Optional) Add your `GOOGLE_AI_API_KEY` in Space Settings → Repository secrets for topic categorization
5. Your app will be live!

## 🎓 Example: Reith Lectures

The Reith Lectures are available as a podcast:

**RSS Feed:** `https://podcasts.files.bbci.co.uk/p00fzl9g.rss`

Use the Download tab in the Gradio app or:

```python
from src.scraper.rss_scraper import RSScraper

scraper = RSScraper()
scraper.download_episodes('https://podcasts.files.bbci.co.uk/p00fzl9g.rss', limit=10)
```

## 🔧 Troubleshooting

### Whisper Transcription Issues

**Whisper is slow:**
- Use a smaller model: `tiny` or `base` for faster transcription
- The `medium` and `large` models require significant CPU/GPU resources
- Consider using a GPU-enabled machine for 10-100x speedup

**Out of memory errors:**
- Switch to a smaller Whisper model
- Process shorter audio segments
- Close other applications to free up RAM

### Audio Processing

**FFmpeg not found:**
- Make sure FFmpeg is installed: `ffmpeg -version`
- On Linux: `sudo apt install ffmpeg`
- On macOS: `brew install ffmpeg`
- On Windows: Download from https://ffmpeg.org/download.html and add to PATH

**Audio download fails:**
- Check your internet connection
- Verify the RSS feed URL is correct
- Some BBC content may be region-restricted

### Topic Categorization Issues

**"Google AI API key not configured" error:**
- Make sure you've created a `.env` file (copy from `.env.example`)
- Add your API key: `GOOGLE_AI_API_KEY=your_key_here`
- Get a free key at: https://makersuite.google.com/app/apikey
- Restart the application after adding the key

**"Model not found" error:**
- The app uses `gemini-flash-latest` model
- Make sure your API key is valid and active
- Check if you have access to Gemini API in your region

### get_iplayer Issues

**get_iplayer not working:**
- Update the cache: `get_iplayer --refresh`
- Check if BBC iPlayer is available in your region
- RSS feeds are recommended as a more reliable alternative

## 🎓 Use Cases

- **Researchers**: Analyze BBC documentaries and lectures
- **Students**: Study and reference educational content
- **Journalists**: Search through interview archives
- **Podcast Enthusiasts**: Build a searchable podcast library
- **Accessibility**: Generate transcripts for hearing-impaired users

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## 📄 License

MIT License - Free for personal and educational use.

## ⚠️ Disclaimer

This tool is for **personal use and educational purposes only**. 

- Respect BBC's terms of service and copyright
- Do not redistribute downloaded content
- Transcripts are generated by AI and may contain errors
- Use responsibly and ethically

## 🙏 Acknowledgments

- **BBC** for providing excellent audio content
- **OpenAI** for the Whisper model
- **Google** for Gemini AI (topic categorization)
- All the open-source contributors who made this possible

## 📞 Support

If you encounter any issues or have questions:
1. Check the [Troubleshooting](#-troubleshooting) section
2. Search existing [GitHub Issues](../../issues)
3. Create a new issue with detailed information

---

**Made with ❤️ for BBC audio enthusiasts and AI learners**
