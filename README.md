# video2txt · Local Video Transcription for AI Agents

> **Free, private, offline video-to-text** — no API keys, no per-minute costs, no cloud upload.
> Built for AI agents and automation pipelines, with a human-in-the-loop batch workflow.

`yt-dlp` → `ffmpeg` → `faster-whisper` (local ASR, CUDA-accelerated) → **txt / srt / vtt / docx**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()

## Why

Cloud transcription services charge per minute and require API keys. This project is a fully local
replica of that workflow: download the audio track, transcribe it on your own machine (GPU or CPU),
and get subtitles, plain text, or a formatted Word document — **free and private**.

It is designed to be invoked **by AI agents** (Claude, Codex, Hermes, custom agents) as a skill/CLI:
deterministic commands, structured output, idempotent retries, and an explicit two-phase
(resolve → confirm → execute) workflow that prevents runaway batch jobs.

## Features

- **Single-link transcription**: `url <video-url>` — download + transcribe in one step
- **Playlist / multi-part expansion**: `playlist <url>` resolves every video in a series/collection
  (Bilibili 合集, YouTube playlists, multi-P videos) with titles and durations
- **Batch execution with human confirmation**: list first → confirm task count → run. Idempotent:
  already-transcribed videos are skipped, so interrupted runs resume seamlessly
- **Parallel pipelines**: `--jobs 2` downloads with N threads and transcribes with N GPU processes
- **4 output formats**: plain text (`.txt`), subtitles (`.srt`), web captions (`.vtt`),
  and a formatted Word document (`.docx`, 黑体 title + 宋体 body + gray timestamps)
- **Domain-term prompting**: built-in civil-engineering/tunneling vocabulary prompt
  (盾构法, 矿山法, 深基坑, …) that measurably improves jargon accuracy; `--prompt` overrides it
- **CUDA-accelerated** when an NVIDIA GPU is present; falls back to CPU automatically
- **Offline-first**: models are cached locally; no telemetry, no upload

## Keywords

video transcription · speech-to-text · ASR · whisper · faster-whisper · subtitle extraction ·
captions · YouTube · Bilibili · TikTok · Douyin · Xiaohongshu · WeChat Channels · podcast-to-text ·
meeting notes · playlist batch · agent skill · AI agent tool · MCP-friendly CLI · automation ·
yt-dlp · ffmpeg · CUDA · GPU inference · docx · srt · vtt · 视频转文字 · 语音识别 · 字幕提取 ·
本地转录 · 批量转录 · 合集解析

## Requirements

- Python 3.10+ (3.12 recommended)
- `ffmpeg` on PATH
- [uv](https://docs.astral.sh/uv/) (optional but recommended) or pip
- NVIDIA GPU + CUDA 12 for GPU acceleration (optional; CPU works)

## Install

```bash
# 1. Create an x86_64 venv (important: ctranslate2 ships no 32-bit wheels)
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe yt-dlp faster-whisper python-docx   # Windows
# uv pip install --python .venv/bin/python     yt-dlp faster-whisper python-docx   # Linux/macOS

# 2. Optional: CUDA acceleration (NVIDIA GPU)
uv pip install --python .venv/Scripts/python.exe "ctranslate2[cuda12]"

# 3. ffmpeg
#   Windows: winget install Gyan.FFmpeg
#   macOS:   brew install ffmpeg
#   Debian/Ubuntu: sudo apt install ffmpeg
```

## Models

Download a `Systran/faster-whisper-*` model from HuggingFace into `models/faster-whisper-<size>/`
(`model.bin`, `config.json`, `tokenizer.json`, `vocabulary.txt` or `.json`).

```bash
python -m videosays_local.download_model small     # ~460 MB  — fastest, readable output
python -m videosays_local.download_model medium    # ~1.5 GB  — balanced accuracy/speed (recommended)
python -m videosays_local.download_model large-v3  # ~2.9 GB  — best accuracy (esp. Chinese)
```

| Model | Size | Quality | Speed (GPU) | Best for |
|---|---|---|---|---|
| `small` | ~460 MB | ★★ readable, jargon slips | ~7× real-time | quick drafts, CPU-only machines |
| `medium` | ~1.5 GB | ★★★ good balance | ~4× real-time | **default choice** for most use |
| `large-v3` | ~2.9 GB | ★★★★ best (Chinese/accents) | ~3× real-time | archive-grade transcripts |

> In regions where huggingface.co is unreachable, the mirror
> `https://hf-mirror.com` (or ModelScope `Systran/faster-whisper-*`) can be used.
> Any local directory containing the four files above also works.

## Usage

```bash
python transcribe.py url "<video-url>" --model large-v3 --out outputs

# Phase 1 — resolve a playlist/collection into a manifest (human review)
python transcribe.py playlist "<collection-url>" --out outputs

# Phase 2 — execute the manifest (skips already-done items; resume-safe)
python transcribe.py batch outputs/manifest.json --model large-v3 --out outputs --jobs 2

# Regenerate .docx from existing .srt without re-running ASR
python transcribe.py docx --out outputs

# Inspect the output cache
python transcribe.py cache --out outputs
```

### Human-in-the-loop workflow

1. **Resolve** — `playlist <url>` lists every part with title + duration
2. **Confirm** — a human (or the calling agent's user) approves the task count
3. **Execute** — `batch manifest.json` transcribes each item, skipping completed ones
4. **Deliver** — one `NNN_<title>.txt` / `.srt` / `.vtt` / `.docx` per video

## Performance

| Model | Language quality | Speed (typical NVIDIA GPU) | Speed (CPU only) |
|---|---|---|---|
| `small` | readable | ~7× real-time | ~4× real-time |
| `large-v3` | best (esp. Chinese) | ~3× real-time | slow — GPU recommended |

Two concurrent large-v3 workers fit comfortably in an 8 GB GPU (≈3 GB per model in FP16).

## Known limitations

- Speech-to-text accuracy is bounded by the underlying model: regional accents and rare jargon can
  still slip (e.g. 深基坑 → 升级根). Domain `--prompt` vocabularies mitigate this.
- Some sites (e.g. Bilibili) rate-limit downloads; occasional `media_unavailable` errors are
  resolved with `--cookies-from-browser edge` or a retry.
- First model load includes CUDA init (~1–2 min); subsequent files transcribe quickly.

## Comparison with cloud transcription

| Capability | Cloud (e.g. videosays) | video2txt |
|---|---|---|
| Cost | per-minute billing, API key | **free, offline** |
| Idempotency | 30-day result reuse | local file cache, resume-safe |
| Batch | submit links file | resolve → confirm → execute |
| Formats | timeline/srt/vtt | txt/srt/vtt/docx |
| Privacy | audio uploaded | **audio never leaves your machine** |

## As an agent skill

This repository is packaged as an installable skill for agent runtimes that read `SKILL.md`
frontmatter (e.g. Hermes Agent, Claude Code, Codex). Drop the directory into your skills folder,
and the agent gains a `videosays-local`-style capability: it can transcribe video links, expand
collections, run confirmed batches, and hand back txt/srt/vtt/docx files — all locally.

Trigger phrases for agents: 转录视频 / 视频转文字 / 提取字幕 / 本地转录 / batch transcribe /
video to text / speech to text / subtitles.

## License

MIT
