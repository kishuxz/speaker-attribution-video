#!/usr/bin/env python3
"""Compatibility wrapper. Prefer ``python scripts/verify.py``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> int:
    path = Path(__file__).with_name("verify.py")
    spec = importlib.util.spec_from_file_location("sav_verify", path)
    if spec is None or spec.loader is None:
        print("unable to load scripts/verify.py", file=sys.stderr)
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
