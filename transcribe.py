#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
videosays-local: 本地视频转文字 CLI（yt-dlp 下载 + faster-whisper 本地 ASR）
复现 videosays 云端工作流，但零 API 费用。

命令：
  python transcribe.py url <链接> [--model small|medium|large-v3] [--out <dir>]
  python transcribe.py playlist <合集/多P链接> [--out <dir>]   # 阶段1: 解析清单
  python transcribe.py batch <清单文件> [--model ...] [--out <dir>]  # 阶段2: 执行(跳过已完成)
  python transcribe.py cache                                   # 查看已转写缓存
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.0.0"
DEFAULT_MODEL = "small"  # 中文 small 够用；追求精度 medium
CPU_THREADS = 4  # ASR CPU 线程上限（保留办公裕量），可 --cpu-threads 覆盖
DEFAULT_OUT = Path(__file__).resolve().parent / "outputs"


# ---------- 路径工具 ----------
FFMPEG_BIN = None  # 找到后缓存


def find_ffmpeg() -> str | None:
    """定位 ffmpeg：PATH -> winget 安装目录。返回 bin 目录。"""
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return str(Path(exe).parent)
    # winget Gyan.FFmpeg 安装位置
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if base.exists():
        for f in base.rglob("ffmpeg.exe"):
            return str(f.parent)
    return None


def ensure_ffmpeg_on_path():
    """把 ffmpeg bin 目录注入 PATH，保证 yt-dlp 能转 wav。"""
    global FFMPEG_BIN
    if FFMPEG_BIN is None:
        FFMPEG_BIN = find_ffmpeg()
    if FFMPEG_BIN and FFMPEG_BIN not in os.environ.get("PATH", ""):
        os.environ["PATH"] = FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")


def get_venv_python() -> str:
    here = Path(__file__).resolve().parent
    for cand in (here / ".venv" / "Scripts" / "python.exe",
                 here / ".venv" / "bin" / "python"):
        if cand.exists():
            return str(cand)
    return sys.executable


def run_py(args, cwd=None) -> subprocess.CompletedProcess:
    """用本 skill 的 venv python 运行子命令，避免污染 Anaconda。"""
    env = os.environ.copy()
    here = str(Path(__file__).resolve().parent)
    env["PYTHONPATH"] = here + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([get_venv_python(), *args], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


# ---------- 链接解析 ----------
def bvid_from_url(url: str) -> str:
    m = re.search(r"(BV[0-9A-Za-z]{10})", url)
    return m.group(1) if m else re.sub(r"[^\w\-.]", "_", url)[:60]


def page_tag(url: str) -> str:
    """分P标识：BVxxx 单P返回 None；p=2 返回 p02"""
    m = re.search(r"[?&]p=(\d+)", url)
    return f"p{int(m.group(1)):02d}" if m else None


def normalize_title(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", title.strip())[:80]


# ---------- 阶段1: 解析合集/多P清单 ----------
def resolve_playlist(url: str, out_dir: Path) -> list:
    """用 yt-dlp --flat-playlist 列出全部分P/合集条目，写入清单 json + txt。"""
    print(f"[1/2] 解析链接: {url}")
    cmd = [get_venv_python(), "-m", "yt_dlp", "--flat-playlist", "-J", "--no-warnings", url]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp 解析失败:\n{r.stderr[-2000:]}")
    data = json.loads(r.stdout)
    entries = data.get("entries") or []
    items = []
    for i, e in enumerate(entries, 1):
        if not e:
            continue
        item_url = e.get("url") or e.get("webpage_url") or ""
        if not item_url:
            continue
        if not item_url.startswith("http"):
            item_url = "https://www.bilibili.com/video/" + item_url
        items.append({"idx": i, "id": e.get("id", ""), "title": e.get("title", ""),
                      "url": item_url, "duration": e.get("duration")})
    if not items:
        # 单视频（非合集）：flat 模式 entries 为空，退化为单条
        items = [{"idx": 1, "id": data.get("id", ""), "title": data.get("title", ""),
                  "url": url, "duration": data.get("duration")}]

    # 补全缺失标题/时长：flat 模式（尤其 bilibili 合集）只返回 BV 号
    missing = [it for it in items if not it.get("title")]
    if missing:
        print(f"      补全 {len(missing)} 条标题（yt-dlp 单条查询，约 3s/条）...")
        for it in missing:
            try:
                r = subprocess.run(
                    [get_venv_python(), "-m", "yt_dlp", "--no-playlist", "--skip-download",
                     "--print", "%(title)s|%(duration)s", "--no-warnings", it["url"]],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=30)
                if r.returncode == 0 and r.stdout.strip():
                    t, _, d = r.stdout.strip().partition("|")
                    it["title"] = t
                    if d:
                        it["duration"] = float(d)
            except Exception:
                pass
            if not it.get("title"):
                it["title"] = f"video_{it['idx']}"
    manifest = out_dir / "manifest.json"
    manifest.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = "\n".join(f"{it['idx']}\t{it['title']}\t{it['url']}" for it in items)
    (out_dir / "manifest.txt").write_text(lines, encoding="utf-8")
    return items


# ---------- 阶段2: 单条下载+转写 ----------
def download_audio(item: dict, out_dir: Path, force: bool = False) -> Path:
    """只下载音轨（并行用）。返回 wav 路径。"""
    ensure_ffmpeg_on_path()
    idx = item["idx"]
    bvid = bvid_from_url(item["url"])
    wav_path = out_dir / f"{idx:03d}_{bvid}.wav"
    if wav_path.exists() and not force:
        return wav_path
    print(f"  [dl {idx}] 下载: {item.get('title','')[:30]}")
    cmd = [get_venv_python(), "-m", "yt_dlp",
           "-f", "bestaudio/best", "-x", "--audio-format", "wav",
           "--audio-quality", "0", "-o", str(out_dir / f"{idx:03d}_{bvid}.%(ext)s"),
           "--no-playlist", "--no-warnings", item["url"]]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"yt-dlp 下载失败 {item['url']}:\n{r.stderr[-1500:]}")
    if not wav_path.exists():
        cands = list(out_dir.glob(f"{idx:03d}_{bvid}.*"))
        raise RuntimeError(f"未找到音频文件: {cands}")
    print(f"  [dl {idx}] ✅ {wav_path.name}")
    return wav_path


def transcribe_one(item: dict, out_dir: Path, model: str, force: bool = False) -> str:
    ensure_ffmpeg_on_path()
    idx = item["idx"]
    title = item.get("title") or f"video_{idx}"
    url = item["url"]
    model = item.get("model") or model  # 条目级覆盖：manifest 可指定 large-v3
    bvid = bvid_from_url(url)
    ptag = page_tag(url)
    key = f"{bvid}_{ptag}" if ptag else bvid
    safe = normalize_title(title)
    txt_path = out_dir / f"{idx:03d}_{safe}.txt"

    # 幂等：已有结果则跳过（对应云端 30 天复用）
    if txt_path.exists() and not force:
        print(f"  [{idx}] 已转写（缓存命中，跳过）: {title}")
        return str(txt_path)

    print(f"  [{idx}] 开始: {title}")
    print(f"       {url}")

    # 1) 下载音频（若未下载）
    wav_path = out_dir / f"{idx:03d}_{bvid}.wav"
    if not wav_path.exists() or force:
        wav_path = download_audio(item, out_dir, force)

    # 2) faster-whisper 转写（在 venv 内运行）
    print(f"       ASR 转写中（model={model}）...")
    t0 = time.time()
    r = run_py(["-m", "videosays_local.asr", "--wav", str(wav_path),
                "--model", model, "--out", str(txt_path),
                "--cpu-threads", str(CPU_THREADS)])
    if r.returncode != 0:
        raise RuntimeError(f"ASR 失败 {title}:\n{r.stderr[-2000:]}")
    print(f"       ✅ {time.time()-t0:.0f}s: {txt_path.name}")
    return str(txt_path)


def srt_to_docx(srt_path: Path, out_base: str):
    """从已有 .srt 文件生成 .docx（不重跑 ASR）。
    解析 "00:00:01,000 --> 00:00:02,500" + 文本 行。
    """
    import re
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from videosays_local.asr import write_docx
    segs = []
    ts_re = re.compile(r"(\d+):(\d+):(\d+)[,. ](\d+) --> (\d+):(\d+):(\d+)[,. ](\d+)")
    text_buf = []
    cur = None

    def flush():
        nonlocal text_buf, cur
        if cur and text_buf:
            segs.append(("".join(text_buf).strip(), cur[0], cur[1]))
        text_buf, cur = [], None

    for line in srt_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        m = ts_re.match(s)
        if m:
            flush()  # 遇到新时间戳，先落盘上一段
            cur = (int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000,
                   int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + int(m[8]) / 1000)
        elif s and cur:
            text_buf.append(s)
        elif not s:
            flush()
    flush()
    write_docx(out_base, srt_path.stem, segs)
    print(f"  [docx] {srt_path.name} -> {out_base}.docx ({len(segs)} 段)")


# ---------- 批量执行 ----------
def run_batch(manifest: Path, out_dir: Path, model: str, force: bool = False, jobs: int = 1, dl_jobs: int = 3):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    items = json.loads(manifest.read_text(encoding="utf-8"))
    done, failed = 0, []

    # 阶段1: 并行下载缺失音轨（网络 IO，不占 CPU/GPU；dl_jobs 默认 3 线程）
    dl_n = max(1, min(dl_jobs, 6))
    print(f"--- 并行下载音轨（{dl_n} 线程）---")
    with ThreadPoolExecutor(max_workers=dl_n) as ex:
        futs = {ex.submit(download_audio, it, out_dir, force): it for it in items}
        for f in as_completed(futs):
            it = futs[f]
            try:
                f.result()
            except Exception as e:
                print(f"  ❌ [dl {it['idx']}] {e}")
                failed.append((it["idx"], str(e)))
    # 阶段2: 转写（jobs=1 默认单进程，GPU 裕量；可 --jobs 2 双并发）
    if jobs > 1:
        print(f"--- 并行转写（{jobs} 并发, GPU）---")
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = {ex.submit(transcribe_one, it, out_dir, model, force): it
                    for it in items if it["idx"] not in [f for f, _ in failed]}
            for f in as_completed(futs):
                it = futs[f]
                try:
                    f.result()
                    done += 1
                except Exception as e:
                    print(f"  ❌ [{it['idx']}] {it.get('title','')}: {e}")
                    failed.append((it["idx"], str(e)))
    else:
        for it in items:
            if it["idx"] in [f for f, _ in failed]:
                continue
            try:
                transcribe_one(it, out_dir, model, force)
                done += 1
            except Exception as e:
                print(f"  ❌ [{it['idx']}] {it.get('title','')}: {e}")
                failed.append((it["idx"], str(e)))

    print(f"\n=== 完成 {done}/{len(items)}，失败 {len(failed)} ===")
    for i, e in failed:
        print(f"  fail #{i}: {e}")
    return 1 if failed else 0


# ---------- main ----------
def main():
    global CPU_THREADS
    ap = argparse.ArgumentParser(description="videosays-local 本地视频转文字")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_url = sub.add_parser("url", help="单链接转写")
    p_url.add_argument("url")
    p_url.add_argument("--model", default=DEFAULT_MODEL)
    p_url.add_argument("--out", default=str(DEFAULT_OUT))
    p_url.add_argument("--force", action="store_true")
    p_url.add_argument("--cpu-threads", type=int, default=CPU_THREADS)

    p_pl = sub.add_parser("playlist", help="阶段1: 解析合集/多P -> 生成清单（人工核对）")
    p_pl.add_argument("url")
    p_pl.add_argument("--out", default=str(DEFAULT_OUT))

    p_bt = sub.add_parser("batch", help="阶段2: 执行清单（跳过已完成）")
    p_bt.add_argument("manifest", type=Path)
    p_bt.add_argument("--model", default=DEFAULT_MODEL)
    p_bt.add_argument("--out", default=str(DEFAULT_OUT))
    p_bt.add_argument("--force", action="store_true")
    p_bt.add_argument("--cpu-threads", type=int, default=CPU_THREADS)
    p_bt.add_argument("--dl-jobs", type=int, default=3,
                      help="下载并行线程数（网络IO不占CPU/GPU，默认3）")
    p_bt.add_argument("--jobs", type=int, default=1,
                      help="GPU转写并发: 1=单进程(留裕量,默认); 2=双进程(更快但占满GPU)")

    p_cache = sub.add_parser("cache", help="查看输出缓存")
    p_cache.add_argument("--out", default=str(DEFAULT_OUT))

    p_docx = sub.add_parser("docx", help="从已有 .srt 批量生成 .docx（不重跑 ASR）")
    p_docx.add_argument("--out", default=str(DEFAULT_OUT))
    p_docx.add_argument("--all", action="store_true", help="处理输出目录全部 srt")

    args = ap.parse_args()
    if hasattr(args, "cpu_threads") and args.cpu_threads:
        CPU_THREADS = args.cpu_threads
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.cmd == "url":
        item = {"idx": 1, "title": None, "url": args.url}
        try:
            # 先尝试解析标题
            r = run_py(["-m", "yt_dlp", "--no-playlist", "--print", "%(title)s",
                        "--no-warnings", "--skip-download", args.url])
            if r.returncode == 0 and r.stdout.strip():
                item["title"] = r.stdout.strip()
        except Exception:
            pass
        transcribe_one(item, out_dir, args.model, args.force)

    elif args.cmd == "playlist":
        items = resolve_playlist(args.url, out_dir)
        print(f"\n=== 解析到 {len(items)} 个视频 ===")
        for it in items:
            dur = f"({it['duration']}s)" if it.get("duration") else ""
            print(f"  #{it['idx']:03d} {it['title']} {dur}")
        print(f"\n清单已写入: {out_dir / 'manifest.txt'}")
        print("人工核对数量无误后执行: python transcribe.py batch "
              f"{out_dir / 'manifest.json'} --out {out_dir}")

    elif args.cmd == "batch":
        sys.exit(run_batch(args.manifest, out_dir, args.model, args.force,
                           args.jobs, args.dl_jobs))

    elif args.cmd == "cache":
        files = sorted(out_dir.glob("*.txt"))
        print(f"输出目录: {out_dir}  共 {len(files)} 条转写")
        for f in files:
            print(f"  {f.name}  ({f.stat().st_size//1024} KB)")

    elif args.cmd == "docx":
        srts = sorted(out_dir.glob("*.srt"))
        if not args.all:
            # 只补缺失 .docx 的
            srts = [s for s in srts if not s.with_suffix(".docx").exists()]
        if not srts:
            print("无需生成（所有 srt 已有 docx）")
            return
        print(f"生成 {len(srts)} 个 docx...")
        for s in srts:
            srt_to_docx(s, str(s.with_suffix("")))


if __name__ == "__main__":
    main()
