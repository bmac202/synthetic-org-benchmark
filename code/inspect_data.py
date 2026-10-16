#!/usr/bin/env python3
"""Walk everything downloaded and report what is actually in it.

Run this before writing any analysis. The loaders in loaders/ are written
defensively against several plausible column namings, but no one has published
a schema for most of these deposits, so the first honest step is to look.

    python3 inspect_data.py                       # auto-detect project root
    python3 inspect_data.py --root /Volumes/OWC/BeeOrg
    python3 inspect_data.py --dataset beesbook_2018 --full

Writes logs/schema_report.md alongside the console output.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

TABULAR = {".csv", ".tsv", ".txt", ".dat"}
INTERESTING = TABULAR | {".json", ".graphml", ".xml", ".h5", ".hdf5", ".npy", ".npz", ".pkl", ".feather", ".parquet"}
MAX_PREVIEW_BYTES = 400_000


def human(n: float | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} PB"


def find_root(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if (p / "data" / "raw").is_dir():
            return p
        if (p / "BeeOrg" / "data" / "raw").is_dir():
            return p / "BeeOrg"
        raise SystemExit(f"{p} does not look like the project root")
    here = Path(__file__).resolve().parent
    for cand in (here.parent, here):
        if (cand / "data" / "raw").is_dir():
            return cand
    vols = Path("/Volumes")
    if vols.is_dir():
        for v in vols.iterdir():
            if (v / "BeeOrg" / "data" / "raw").is_dir():
                return v / "BeeOrg"
    raise SystemExit("could not find the project root; pass --root")


def sniff_table(path: Path) -> dict:
    """Read the head of a delimited file and describe it."""
    try:
        with path.open("rb") as fh:
            head = fh.read(MAX_PREVIEW_BYTES)
    except OSError as exc:
        return {"error": str(exc)}
    text = head.decode("utf-8", "replace")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t| ")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if "\t" in sample.splitlines()[0] else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if r]
    if not rows:
        return {"error": "empty"}
    header = rows[0]
    looks_headed = any(any(c.isalpha() for c in cell) for cell in header)
    body = rows[1:6] if looks_headed else rows[:5]
    return {
        "delimiter": repr(delim),
        "columns": header if looks_headed else [f"col{i}" for i in range(len(header))],
        "n_columns": len(header),
        "sample_rows": body,
        "header_detected": looks_headed,
    }


def describe(path: Path, root: Path, full: bool) -> list[str]:
    rel = path.relative_to(root)
    size = path.stat().st_size
    out = [f"\n### `{rel}`", f"- size: {human(size)}"]
    suf = path.suffix.lower()

    if suf in TABULAR:
        info = sniff_table(path)
        if "error" in info:
            out.append(f"- could not parse: {info['error']}")
            return out
        out.append(f"- delimiter: {info['delimiter']}  ·  columns: {info['n_columns']}"
                   f"  ·  header row detected: {info['header_detected']}")
        out.append(f"- columns: `{', '.join(str(c) for c in info['columns'])}`")
        out.append("- first rows:")
        for r in info["sample_rows"]:
            cells = r if full else r[:12]
            tail = "" if full or len(r) <= 12 else f"  ... (+{len(r)-12} more)"
            out.append(f"    - `{' | '.join(str(c) for c in cells)}`{tail}")
    elif suf == ".json":
        try:
            with path.open("rb") as fh:
                blob = json.loads(fh.read(MAX_PREVIEW_BYTES).decode("utf-8", "replace"))
            if isinstance(blob, dict):
                out.append(f"- JSON object, top-level keys: `{', '.join(list(blob)[:25])}`")
            elif isinstance(blob, list):
                out.append(f"- JSON array of {len(blob)} items")
                if blob and isinstance(blob[0], dict):
                    out.append(f"- item keys: `{', '.join(list(blob[0])[:25])}`")
        except Exception:  # noqa: BLE001
            out.append("- JSON too large or truncated to parse from the head")
    elif suf in {".h5", ".hdf5"}:
        try:
            import h5py  # type: ignore
            with h5py.File(path, "r") as f:
                keys: list[str] = []
                f.visit(lambda k: keys.append(k) or None)
                out.append(f"- HDF5 datasets: `{', '.join(keys[:30])}`")
        except ImportError:
            out.append("- HDF5 (install h5py to inspect: pip3 install h5py)")
        except Exception as exc:  # noqa: BLE001
            out.append(f"- HDF5 unreadable: {exc}")
    elif suf in {".npy", ".npz"}:
        try:
            import numpy as np  # type: ignore
            obj = np.load(path, allow_pickle=True)
            if suf == ".npz":
                out.append(f"- npz arrays: `{', '.join(obj.files[:30])}`")
            else:
                out.append(f"- ndarray shape {obj.shape}, dtype {obj.dtype}")
        except ImportError:
            out.append("- numpy array (install numpy to inspect)")
        except Exception as exc:  # noqa: BLE001
            out.append(f"- unreadable: {exc}")
    elif suf == ".graphml":
        try:
            text = path.read_text(errors="replace")[:4000]
            import re
            keys = re.findall(r'<key[^>]*attr\.name="([^"]+)"[^>]*for="([^"]+)"', text)
            if keys:
                out.append("- graphml attributes: " + ", ".join(f"`{n}` ({w})" for n, w in keys[:20]))
        except Exception:  # noqa: BLE001
            pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root")
    ap.add_argument("--dataset", help="inspect only this dataset directory")
    ap.add_argument("--full", action="store_true", help="print all columns of sample rows")
    ap.add_argument("--max-files", type=int, default=25, help="per dataset (default 25)")
    args = ap.parse_args()

    root = find_root(args.root)
    raw = root / "data" / "raw"
    print(f"Project root: {root}\n")

    lines = [f"# Schema report", f"", f"Project root: `{root}`", ""]
    datasets = sorted(d for d in raw.iterdir() if d.is_dir())
    if args.dataset:
        datasets = [d for d in datasets if d.name == args.dataset]
        if not datasets:
            raise SystemExit(f"no dataset directory named {args.dataset}")

    for d in datasets:
        files = [p for p in sorted(d.rglob("*"))
                 if p.is_file() and not p.name.startswith(".")
                 and p.name not in {"SOURCE.txt", "RESOLVED.json"}]
        total = sum(p.stat().st_size for p in files)
        header = f"\n## {d.name}  —  {len(files)} files, {human(total)}"
        print(header)
        lines.append(header)

        src = d / "SOURCE.txt"
        if src.exists():
            for ln in src.read_text().splitlines():
                if ln.strip():
                    lines.append(f"> {ln}")
            lines.append("")

        # show the interesting ones first, biggest last (headers are usually small)
        ranked = sorted(files, key=lambda p: (p.suffix.lower() not in INTERESTING, p.stat().st_size))
        shown = 0
        for p in ranked:
            if shown >= args.max_files:
                lines.append(f"\n_({len(files) - shown} further files not shown; "
                             f"re-run with --dataset {d.name} --max-files 200)_")
                break
            if p.suffix.lower() not in INTERESTING:
                continue
            block = describe(p, root, args.full)
            print("\n".join(block))
            lines.extend(block)
            shown += 1

        if shown == 0:
            note = "- no tabular/structured files found at the top level (may still be archived or binary)"
            print(note)
            lines.append(note)

    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "schema_report.md").write_text("\n".join(lines))
    print(f"\n\nWritten: {logs / 'schema_report.md'}")
    print("Read that file, then set the column names at the top of each loader in code/loaders/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
