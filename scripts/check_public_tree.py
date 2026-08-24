#!/usr/bin/env python3
"""Fail if the Git index contains prohibited artifacts or likely secrets.

Prints path categories only. Does not print file contents or secret values.
Does not download models. Synthetic fixtures under tests/fixtures/synthetic/ are allowed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ALLOW_PREFIX = "tests/fixtures/synthetic/"

PROHIBITED_SUFFIXES = (
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".wav",
    ".flac",
    ".rttm",
    ".fdx",
    ".gguf",
    ".safetensors",
    ".pt",
    ".pth",
    ".onnx",
    ".ckpt",
    ".wandb",
    ".jsonl",
)

PROHIBITED_PREFIXES = (
    "wandb/",
    "logs/",
    "data/raw/",
    "data/ground_truth/",
    "data/training/",
)

PROHIBITED_NAMES = {".env"}

SECRET_PATTERNS = (
    ("huggingface_token", re.compile(rb"hf_[A-Za-z0-9]{20,}")),
    ("openai_key", re.compile(rb"sk-[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(rb"ghp_[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(rb"AKIA[0-9A-Z]{16}")),
)

MAX_BYTES = 1_000_000


def tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"])
    return [p.decode() for p in out.split(b"\0") if p]


def is_allowed(path: str) -> bool:
    return path == ALLOW_PREFIX.rstrip("/") or path.startswith(ALLOW_PREFIX)


def main() -> int:
    failures: list[str] = []
    files = tracked_files()
    for path in files:
        if is_allowed(path):
            continue
        name = Path(path).name
        if name in PROHIBITED_NAMES or path in PROHIBITED_NAMES:
            failures.append(f"prohibited-name:{path}")
            continue
        if path.startswith(PROHIBITED_PREFIXES):
            failures.append(f"prohibited-path:{path}")
            continue
        if path.lower().endswith(PROHIBITED_SUFFIXES):
            failures.append(f"prohibited-suffix:{path}")
            continue
        p = Path(path)
        if not p.is_file() or p.is_symlink():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > MAX_BYTES:
            failures.append(f"large-file:{path}")
            continue
        data = p.read_bytes()
        for label, pat in SECRET_PATTERNS:
            if pat.search(data):
                failures.append(f"{label}:{path}")
    if failures:
        print("public-tree check failed:")
        for item in failures:
            print(f"  {item}")
        return 1
    print(f"public-tree check passed ({len(files)} tracked files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
