# videosays-local：本地视频转文字（免费，零 API 密钥）

videosays 云端转录服务的本地免费复刻：`yt-dlp 下载音轨 → ffmpeg 转 wav → faster-whisper 本地 ASR（CUDA 加速）→ txt/srt/vtt/docx`。

不需要任何 API key，不产生转录费用。

## 特性

- **单链接转录**：`url <视频链接>` 一步完成下载+转写
- **Bilibili 合集/多P 解析**：`playlist <合集链接>` 识别全部分P并生成清单（先人工核对任务量再执行）
- **批量任务**：`batch manifest.json --jobs 2` 并行下载+GPU 并行转写，断点续跑（已完成自动跳过）
- **多格式输出**：txt / srt / vtt / **docx**（黑体标题 + 宋体正文 + 灰色时间戳）
- **术语优化**：内置土木/隧道领域提示词（盾构法、矿山法、深基坑等），`--prompt` 可自定义
- **CUDA 加速**：RTX 3070 Ti 上 large-v3 约 3x 实时

## 安装

```bash
# 创建 x86_64 Python 3.12 venv（重要：必须是 x86_64，否则 ctranslate2 无 wheel）
uv venv .venv --python cpython-3.12.x-windows-x86_64
uv pip install --python .venv/Scripts/python.exe yt-dlp faster-whisper python-docx

# 安装 ctranslate2 CUDA 版（有 NVIDIA GPU 时）
uv pip install --python .venv/Scripts/python.exe "ctranslate2[cuda12]"

# ffmpeg（Windows: winget install Gyan.FFmpeg；Linux/macOS: 系统包管理器）
```

## 模型

模型从 HuggingFace `Systran/faster-whisper-*` 获取，放到 `models/faster-whisper-<size>/`（含 `model.bin`、`config.json`、`tokenizer.json`、`vocabulary.txt/.json`）。国内可用 ModelScope 镜像：`Systran/faster-whisper-small|medium|large-v3` 的 `resolve/master/` 文件。

```bash
python -m videosays_local.download_model large-v3   # 从 ModelScope 下载
```

## 用法

```bash
python transcribe.py url "<视频链接>" --model large-v3 --out outputs

# 阶段1：解析合集，生成清单（人工核对）
python transcribe.py playlist "<合集链接>" --out outputs
# 阶段2：执行批量（已完成自动跳过）
python transcribe.py batch outputs/manifest.json --model large-v3 --out outputs --jobs 2

# 从已有 srt 补生成 docx（不重跑 ASR）
python transcribe.py docx --out outputs
```

## 工作流（任务量人工核对）

1. **解析**：`playlist <链接>` 列出全部分P标题+时长
2. **核对**：人工确认数量无误
3. **执行**：`batch manifest.json`，逐条下载+转写，已完成自动跳过
4. **交付**：每视频输出 `NNN_标题.txt` + `.srt` + `.vtt` + `.docx`

## 已知限制

- hf-mirror.com 对模型文件返回 308 重定向到 huggingface.co（国内不可达），模型需本地化（ModelScope 或网盘缓存）
- faster-whisper large-v3 对中文口音仍有少量术语错误（如"深基坑"→"升级根"），可通过 `--prompt` 注入领域词表缓解
- Bilibili 反爬：偶发 `media_unavailable`，可用 `--cookies-from-browser edge` 重试

## 对照 videosays 云端

| 能力 | videosays 云端 | videosays-local |
|---|---|---|
| 费用 | 余额扣费 | 免费 |
| 幂等 | 30 天复用 | 文件缓存跳过 |
| 批量 | batch links.txt | playlist → 核对 → batch manifest |
| 格式 | timeline/srt/vtt | txt/srt/vtt/docx |

## License

MIT
