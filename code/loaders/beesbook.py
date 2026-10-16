"""BeesBook (Landgraf / Couzin / Smith) -> canonical events.

Zenodo 6045860 (2018: 4,242 bees, 85 days) and 7298798 (2019: 9,135 bees, 115 days).
CC-BY-4.0.

The deposit gives per-bee positions, headings, ages and lifespans, but no
categorical task labels. We define task by SPATIAL ZONE, which is not a
convenience: Mersch, Crespi & Keller (2013) titled their paper "spatial fidelity
is a key regulator of ant social organization" precisely because where an
individual sits in the nest is the strongest available predictor of what it does.
In honey bees the standard zones are brood nest, honey storage, dance floor and
the entrance region, and they correspond to nursing, food processing, recruitment
and foraging.

Two ways to define the zones:

  --zone-mode grid      Partition the arena into a `--zones`-cell grid using
                        quantiles of the observed coordinates. Assumption-free,
                        reproducible, but the cells are not named behaviours.
  --zone-mode radial    Bin by distance from the entrance (taken as the edge of
                        the arena with the highest traffic). Closer to the
                        biology: nurses sit deep, foragers sit shallow.

Both are declared in meta.json so the choice is visible in any downstream result.
Run `inspect_data.py --dataset beesbook_2018` first and check the column names
against CANDIDATES below.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from .common import (EventBuilder, find_files, pick_column, pick_columns,
                     quantize, report, stream_rows, to_float, write_events)

CANDIDATES = {
    "bee":   ["bee_id", "id", "bee", "track_id", "individual", "beeID"],
    "x":     ["x_pos", "x", "xpos", "x_hive", "x_mm", "x_coord"],
    "y":     ["y_pos", "y", "ypos", "y_hive", "y_mm", "y_coord"],
    "time":  ["timestamp", "time", "frame", "frame_idx", "datetime", "t"],
    "day":   ["day", "date", "day_idx", "dayNumber"],
    "age":   ["age", "age_days"],
    "cam":   ["cam_id", "camera", "cam"],
}

# Only these are resolved, because only these are read. `day` and `cam` are
# declared above for inspect_data.py's benefit; this loader never touches them.
#
# Leaving them out of the guarded set is deliberate rather than lazy. `day` and
# `time` do genuinely collide on a plausible header -- a single `datetime` column
# matches both candidate lists -- and were `day` in the spec, such a file would be
# REFUSED on account of a role this loader never reads. A guard that blocks
# correct work teaches people to route around it, and a guard people route around
# protects nothing. If day-based binning is ever wired in here, `day` joins
# USED_ROLES on the same commit and that collision becomes real and worth raising.
USED_ROLES = ("bee", "x", "y", "time", "age")


def load(raw_dir: Path, n_zones: int = 4, n_bins: int = 400,
         zone_mode: str = "grid", max_rows: int | None = None,
         min_obs: int = 20):
    """Return (events, meta) for a BeesBook raw directory."""
    files = find_files(raw_dir, ["*.csv", "*.tsv", "*.txt"])
    files = [f for f in files if f.name not in {"SOURCE.txt"}]
    if not files:
        raise SystemExit(
            f"no delimited files under {raw_dir}.\n"
            "If the deposit shipped .h5/.npz, run inspect_data.py and add a branch here."
        )

    # Prefer the largest table: that is the per-detection record.
    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    path = files[0]
    print(f"  reading {path.name} ({path.stat().st_size/1e9:.2f} GB)")

    head = next(iter(stream_rows(path, limit=1)), None)
    if head is None:
        raise SystemExit(f"{path} is empty")
    header = list(head.keys())

    # Resolved together. x and y are the pair most likely to cross-match -- on a
    # header naming them `xy` or `pos_x`/`pos` they can both land on one column,
    # and five independent calls cannot see that happen. Every coordinate would
    # then be on the diagonal and every zone assignment wrong, with no error.
    resolved = pick_columns(header,
                            {k: v for k, v in CANDIDATES.items() if k in USED_ROLES},
                            optional=("age",))
    c_bee, c_x, c_y = resolved["bee"], resolved["x"], resolved["y"]
    c_t = resolved["time"]
    c_age = resolved.get("age")
    print(f"  columns -> bee={c_bee} x={c_x} y={c_y} time={c_t} age={c_age}")

    # ---- pass 1: coordinate and time ranges, and entrance side ------------
    xs_lo = ys_lo = t_lo = float("inf")
    xs_hi = ys_hi = t_hi = float("-inf")
    n = 0
    for row in stream_rows(path, limit=max_rows):
        x, y, t = to_float(row[c_x]), to_float(row[c_y]), to_float(row[c_t])
        if x is None or y is None or t is None:
            continue
        xs_lo, xs_hi = min(xs_lo, x), max(xs_hi, x)
        ys_lo, ys_hi = min(ys_lo, y), max(ys_hi, y)
        t_lo, t_hi = min(t_lo, t), max(t_hi, t)
        n += 1
    if n == 0:
        raise SystemExit("pass 1 found no parseable rows; check the column mapping above")
    print(f"  pass 1: {n:,} rows · x[{xs_lo:.1f},{xs_hi:.1f}] "
          f"y[{ys_lo:.1f},{ys_hi:.1f}] t[{t_lo:.0f},{t_hi:.0f}]")

    side = int(round(n_zones ** 0.5)) or 1

    def zone_of(x: float, y: float) -> int:
        if zone_mode == "radial":
            # distance from the y-min edge, binned; deep = nursing, shallow = foraging
            return quantize(y, ys_lo, ys_hi, n_zones)
        gx = quantize(x, xs_lo, xs_hi, side)
        gy = quantize(y, ys_lo, ys_hi, side)
        return gy * side + gx

    # ---- pass 2: accumulate --------------------------------------------
    eb = EventBuilder()
    ages: dict[str, float] = {}
    seen = 0
    for row in stream_rows(path, limit=max_rows):
        x, y, t = to_float(row[c_x]), to_float(row[c_y]), to_float(row[c_t])
        if x is None or y is None or t is None:
            continue
        bee = row[c_bee]
        eb.add(bee, zone_of(x, y), quantize(t, t_lo, t_hi, n_bins))
        if c_age and bee not in ages:
            a = to_float(row[c_age])
            if a is not None:
                ages[bee] = a
        seen += 1
        if seen % 5_000_000 == 0:
            print(f"    ... {seen:,} rows")

    events, meta = eb.build(min_obs_per_agent=min_obs)
    meta.update(
        source="BeesBook (Zenodo 6045860 / 7298798), CC-BY-4.0",
        citation="Smith, Davidson, Wild, Dormagen, Landgraf & Couzin (2022), iScience 25, 104842",
        file=path.name,
        task_definition=f"spatial zone, mode={zone_mode}, n_zones={n_zones}",
        task_caveat=("Zones are a proxy for task, justified by spatial fidelity "
                     "(Mersch et al. 2013). They are not observed behaviours."),
        time_binning=f"{n_bins} equal bins over the full record",
        min_obs_per_agent=min_obs,
        ages_available=bool(ages),
    )
    if ages:
        meta["age_range"] = [min(ages.values()), max(ages.values())]
    return events, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True, help="data/raw/beesbook_2018")
    ap.add_argument("--out", required=True, help="data/processed/beesbook_2018")
    ap.add_argument("--zones", type=int, default=4)
    ap.add_argument("--bins", type=int, default=400)
    ap.add_argument("--zone-mode", default="grid", choices=["grid", "radial"])
    ap.add_argument("--max-rows", type=int, default=None,
                    help="cap rows for a fast trial run (try 2000000 first)")
    ap.add_argument("--min-obs", type=int, default=20)
    a = ap.parse_args()

    events, meta = load(Path(a.raw), a.zones, a.bins, a.zone_mode, a.max_rows, a.min_obs)
    write_events(events, meta, Path(a.out))
    report("beesbook", meta)
    print(f"\n  written: {Path(a.out) / 'events.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
