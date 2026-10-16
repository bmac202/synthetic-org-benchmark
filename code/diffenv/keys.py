"""Credential loading. The only module that touches keys.env.

Rules: load into the process environment, never return the values to a caller, never log
them, never copy them anywhere. `describe()` reports only which names are set and their
lengths, so a report can say "loaded" without saying what.
"""
from __future__ import annotations

import os
from typing import Dict, List

KEY_NAMES = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
DEFAULT_PATHS = ("keys.env", "../keys.env", os.path.expanduser("~/keys.env"),
                 "/mnt/user-data/uploads/OS_Special_Issue/keys.env")


def load_keys(path: str | None = None, override: bool = False) -> List[str]:
    """Read KEY=value lines from keys.env into os.environ. Returns the names loaded."""
    candidates = [path] if path else list(DEFAULT_PATHS)
    loaded: List[str] = []
    for p in candidates:
        if not p or not os.path.isfile(p):
            continue
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k in KEY_NAMES and v and (override or not os.environ.get(k)):
                    os.environ[k] = v
                    loaded.append(k)
        break
    return loaded


def describe() -> Dict[str, str]:
    """Safe to print: name -> 'set (n chars)' or 'missing'. Never the value."""
    return {k: (f"set ({len(os.environ[k])} chars)" if os.environ.get(k) else "missing") for k in KEY_NAMES}


def scrub(text: str) -> str:
    """Replace any loaded key that appears in `text` — belt and braces for logs."""
    for k in KEY_NAMES:
        v = os.environ.get(k)
        if v and v in text:
            text = text.replace(v, f"<{k}>")
    return text
