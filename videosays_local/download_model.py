#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 ModelScope 下载 faster-whisper 模型到本地目录（国内直连，绕开 huggingface.co）。
用法: python -m videosays_local.download_model [small|medium|large-v3] [目标目录]
默认: small -> models/faster-whisper-small
"""
import os
import sys
from pathlib import Path
from urllib.request import urlopen

# ModelScope 仓库与文件清单（与 HF Systran/faster-whisper-* 一致）
REPOS = {
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}
FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
BASE = "https://modelscope.cn/models/{repo}/resolve/master/{file}"


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
        try:
            with urlopen(url, timeout=120) as r, open(target, "wb") as out:
                total = 0
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    total += len(chunk)
            print(f"    OK {total/1e6:.1f} MB")
        except Exception as e:
            print(f"    FAIL {f}: {e}")
            target.unlink(missing_ok=True)
            raise
    print("✅ 模型就绪:", dest_dir)
    return dest_dir


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "small"
    here = Path(__file__).resolve().parent.parent
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else here / "models" / f"faster-whisper-{name}"
    download(name, dest)
