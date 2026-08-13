---
name: videosays-local
description: 本地视频转文字（免费，零 API 密钥）——yt-dlp 下载音轨 + ffmpeg 转 wav + faster-whisper 本地 ASR（CUDA 加速）。支持单链接转录、Bilibili 合集/多P解析、批量任务（先列清单人工核对任务量再执行）、断点续跑（已完成自动跳过）、输出 txt/srt/vtt/docx。关键词/触发词：转录视频、视频转文字、提取字幕、语音转文字、本地转录、批量转录、bilibili合集、视频下载转写、video transcription、speech-to-text、ASR、whisper、subtitle extraction、captions、YouTube transcript、TikTok、Douyin、小红书、字幕文件、srt、vtt、docx、AI agent video transcription、video to text。
version: "1.2.0"
---

# videosays-local：本地视频转文字（videosays 免费复刻）

videosays 云端工作流的本地免费复刻：`yt-dlp 下载音轨 → ffmpeg 转 wav → faster-whisper 本地 ASR（RTX 3070Ti CUDA）→ txt/srt/vtt`。**不需要 API key，零转录费用**。

## 环境（已装好，无需重复安装）

- 工具目录：`D:\Documents\hermes_work\YWork\videosays-local\`
  - `transcribe.py` — 主 CLI
  - `videosays_local/asr.py` — faster-whisper 转写核心（自动 CUDA/CPU 选择 + 术语提示词 + 段落去重）
  - `videosays_local/download_model.py` — ModelScope 模型下载（备用，模型已本地化无需再下）
  - `.venv\` — 独立 Python 3.12 x86_64 venv（yt-dlp + faster-whisper + ctranslate2[cuda12]）
  - `models\faster-whisper-large-v3\` — **large-v3 完整模型（2.9GB，用户网盘缓存复制）**
  - `models\faster-whisper-small\` — small 模型（461MB，兜底）
  - `outputs\` — 转录输出目录
- ffmpeg 9.0：winget 安装（Gyan.FFmpeg），脚本自动定位并注入 PATH
- GPU：RTX 3070 Ti Laptop 8GB（ctranslate2 CUDA 检测到，`device=auto` 自动启用）

## 命令

```powershell
$py = "D:\Documents\hermes_work\YWork\videosays-local\.venv\Scripts\python.exe"
$cli = "D:\Documents\hermes_work\YWork\videosays-local\transcribe.py"

# 1) 单链接转录（下载+ASR 一步完成；默认 large-v3 + CUDA）
& $py $cli url "<视频链接>" --model large-v3 --out "D:\...\outputs"

# 2) 合集/多P 解析（阶段1：只列清单，人工核对任务量）
& $py $cli playlist "<合集链接或含?p=的多P链接>" --out "D:\...\outputs"
#    -> 打印每个分P标题+时长，写入 outputs\manifest.json / manifest.txt

# 3) 批量执行（阶段2：跑清单，已完成自动跳过=断点续跑）
& $py $cli batch "D:\...\outputs\manifest.json" --model large-v3 --out "D:\...\outputs"

# 4) 从已有 srt 补生成 docx（不重跑 ASR）
& $py $cli docx --out "D:\...\outputs"

# 5) 查看输出缓存
& $py $cli cache --out "D:\...\outputs"
```

> PowerShell 下 `& $py` 若被工具层误判为 backgrounding，改用：
> `cmd /c "set PYTHONPATH=D:\...\videosays-local&& `"$py`" `"$cli`" url `"<链接>`""`

## 工作流（严格两阶段，任务量先人工核对——用户铁律）

1. **解析**：`playlist <链接>` 解析合集/多P全部分P（yt-dlp `--flat-playlist`），列出 `#001 标题 (时长)` 清单
2. **核对**：把清单展示给用户确认数量无误后才允许执行（**开始任务前人工核对任务量**）
3. **执行**：用户确认后 `batch manifest.json`，逐条下载+转写，已完成条目自动跳过（幂等，对应云端 30 天复用）
4. **交付**：每视频输出 `NNN_标题.txt` + `.srt` + `.vtt` + `.docx`

## 模型选择

| 模型 | 位置 | 质量 | 速度（3070Ti CUDA） |
|---|---|---|---|
| `large-v3`（默认） | models/ 本地 | ★★★★ 中文最好 | ~3x 实时（265s 视频 83s） |
| `medium` | models/ 本地 | ★★★ 均衡 | ~4x 实时 |
| `small` | models/ 本地 | ★★ 可读但术语错多 | ~7x 实时 |

- `medium` 为均衡档（~1.5GB，ModelScope 完整版已下载到 models/）；命令行 `--model medium` 切换
- 模型按需从本地目录加载；`python -m videosays_local.download_model <size>` 可随时补下载

## 术语优化（中文工程视频关键）

- asr.py 内置土木/隧道领域 initial_prompt 提示词（盾构法、矿山法、深基坑、钢筋混凝土等）
- 实测效果：盾构法/矿山法/明挖法/钢筋混凝土/钢结构 全部正确；残余错词（深基坑→升级根、他山之石→他山之士、延性→原性）为 large-v3 中文口音固有局限
- 新领域可用 `--prompt "自定义术语列表"` 覆盖默认提示词

## 已验证（2026-08-13）

- [x] BV1ap421Z7Vh 端到端：playlist 解析 → url 转录 265s 视频
- [x] small 38s / large-v3 CUDA 83s（CPU small 实测）
- [x] **合集解析实测**：「隧道访谈」合集（space.bilibili.com/1468538555/channel/collectiondetail?sid=3591570）→ 94 个分P全部识别，标题/时长经 yt-dlp 单条查询补全（flat 模式只给 BV 号），清单无缺失
- [x] batch 幂等：重跑跳过已完成（缓存命中）
- [x] 段落重复问题：VAD 边界重叠 → 后处理去重修复
- [x] 模型：用户网盘 HF hub 缓存（blobs）平铺复制到 models/（snapshot 符号链接需按 Target 精确映射，large-v3 用 vocabulary.json 非 txt）
- [x] 环境：win11 + uv Python 3.12 x86_64 + winget ffmpeg 9.0 + ctranslate2[cuda12] 4.8.1（faster-whisper 1.2.1 兼容）

## 陷阱与注意事项

- **uv 默认可能选中 x86 Python**（`windows-x86`）导致 ctranslate2 无 wheel：必须 `uv python install cpython-3.12.x-windows-x86_64` 后 `uv venv --python <x86_64路径>`
- **hf-mirror.com 对 resolve 路径返回 308 重定向到 huggingface.co（不可达）**：模型必须本地化（ModelScope 或网盘缓存），不能依赖 HF 下载
- **PowerShell `&` 调用符**：Hermes terminal 工具层把 `& $var` 误判为 backgrounding，必须 `cmd /c "`"path`" args"` 包裹
- **PYTHONPATH 必须包含 videosays-local 目录**，否则 `-m videosays_local.asr` 找不到模块
- **bilibili 反爬**：失败报 `media_unavailable`，可用 `--cookies-from-browser edge` 重试
- **幂等**：已有 `NNN_标题.txt` 即跳过；`--force` 强制重转；batch 可随时中断重跑（断点续跑）
- **ctranslate2 版本**：cuda12 extra 会升到 4.8.1（faster-whisper 1.2.1 兼容；若报不兼容降回 `ctranslate2<4` + CPU 模式）
- **模型加载耗时**：large-v3 CUDA 首次加载 ~1-2 分钟（含 CUDA 初始化），之后每视频纯转写快

## 与 videosays 云端对照

| 能力 | videosays 云端 | videosays-local |
|---|---|---|
| 费用 | 余额扣费 | 免费 |
| 提交 | transcribe → task_id | url 直接本地跑 |
| 轮询 | status 命令 | 同步等待（后台可 notify） |
| 幂等 | 30 天复用 | 文件缓存跳过 |
| 批量 | batch links.txt | playlist → 核对 → batch manifest |
| 格式 | timeline/srt/vtt | txt/srt/vtt/docx |
| 准确率 | 云模型（略高） | large-v3 CUDA 接近，术语靠提示词 |
