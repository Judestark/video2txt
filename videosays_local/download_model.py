#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 ModelScope 下载 faster-whisper 模型到本地目录（国内直连，绕开 huggingface.co）。
用法: python -m videosays_local.download_model [small|medium|large-v3] [目标目录]
默认: small -> models/faster-whisper-small

采用 curl 下载（-C - 断点续传 + 重试），避免 urllib 大文件直连被强制断开。
"""
import os
import subprocess
import sys
from pathlib import Path

# ModelScope 仓库与文件清单（与 HF Systran/faster-whisper-* 一致）
REPOS = {
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}
FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
BASE = "https://modelscope.cn/models/{repo}/resolve/master/{file}"
MAX_RETRY = 8
CHUNK_TIMEOUT = 240  # 每轮 curl 最长秒数（到时自动续传重试）


def curl_download(url: str, target: Path) -> bool:
    """curl -L -C - 断点续传下载。返回是否完整成功。"""
    # 已完整则跳过
    if target.exists() and target.stat().st_size > 0:
        # 无法预知总大小，交给调用方判断；这里仅做存在性跳过
        return True
    cmd = ["curl.exe", "-L", "-C", "-", "-m", str(CHUNK_TIMEOUT),
           "-o", str(target), url]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return r.returncode == 0


def fetch(url: str, target: Path):
    """带重试的下载：curl 断点续传，失败/超时循环续传。"""
    for i in range(1, MAX_RETRY + 1):
        try:
            ok = curl_download(url, target)
        except Exception as e:
            print(f"    retry {i}/{MAX_RETRY}: {e}", flush=True)
            continue
        if ok:
            return
        print(f"    超时/中断，续传 {i}/{MAX_RETRY} ...", flush=True)
    raise RuntimeError(f"下载失败(重试{MAX_RETRY}次): {url}")


def download(name: str, dest_dir: Path) -> Path:
    repo = REPOS[name]
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"下载 {repo} -> {dest_dir}")
    for f in FILES:
        target = dest_dir / f
        if target.exists() and target.stat().st_size > 0:
            print(f"  [跳过] {f} 已存在")
            continue
        url = BASE.format(repo=repo, file=f)
        print(f"  [下载] {f} ...", flush=True)
        fetch(url, target)
        print(f"    OK {target.stat().st_size/1e6:.1f} MB", flush=True)
    print("✅ 模型就绪:", dest_dir)
    return dest_dir


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "small"
    here = Path(__file__).resolve().parent.parent
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else here / "models" / f"faster-whisper-{name}"
    download(name, dest)
