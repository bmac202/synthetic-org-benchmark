"""Run every instrument on whatever real data has been processed so far.

This is the file that makes the argument. It walks `data/processed/`, applies
the same measurement space to every dataset that converted successfully, and
writes one table plus one JSON report.

The output is deliberately laid out so a real colony and a synthetic
organization appear as rows in the SAME table. That is the whole claim of the
proposal in one screenful: division of labour and flexibility are measurable
in a way that does not care whether the agents are bees, employees, or language
models -- and if a row is missing or a number is null, the instrument failed
honestly rather than producing a plausible-looking artifact.

Usage
-----
    python3 run_real_bench.py --root /Volumes/<drive>/BeeOrg
    python3 run_real_bench.py --root ... --synthetic     # add the bench.py rows
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import instruments
import netstats
from loaders.common import read_events


def load_processed(root: Path) -> dict[str, tuple]:
    """Return {key: (events, meta)} for every processed event dataset."""
    out = {}
    proc = root / "data" / "processed"
    if not proc.exists():
        raise SystemExit(f"no processed data at {proc}\n"
                         "  run fetch_data.py first, then the loaders "
                         "(see README.md, step 3).")
    for d in sorted(p for p in proc.iterdir() if p.is_dir()):
        if (d / "events.csv").exists():
            try:
                out[d.name] = read_events(d)
            except Exception as e:                      # noqa: BLE001
                print(f"  ! {d.name}: could not read events.csv ({e})")
    return out


def split_if_disconnected(name: str, log: list, meta: dict) -> dict[str, tuple]:
    """One log file holding several colonies becomes several logs, or none does.

    `loaders.gernat` writes all three of Gernat's colonies into a single
    `interaction_log.csv`, namespaced `trial:id`. Read back as one graph that is
    not a colony: bees in different colonies never meet, so the pooled graph is
    three disconnected components, and Freeman centralization over it is a
    statistic about the union. It still computes, and it still looks like a
    colony-level number, which is the whole danger -- the Mersch loader refuses
    to pool for exactly this reason and the bench was quietly doing it anyway.

    The split fires on evidence rather than on naming. Ids are grouped by their
    namespace prefix, and the log is only split when NO edge crosses a prefix --
    that is, when the prefixes really are separate components. If any edge does
    cross, the prefixes are labels within one interacting population, splitting
    would destroy real edges, and the log is left alone and said to be left
    alone. A colon in an id that is not a namespace therefore costs nothing.
    """
    def ns(node: str) -> str:
        return node.split(":", 1)[0] if ":" in node else ""

    groups = sorted({ns(m["sender"]) for m in log} | {ns(m["recipient"]) for m in log})
    if len(groups) < 2 or "" in groups:
        return {name: (log, meta)}
    crossing = sum(1 for m in log if ns(m["sender"]) != ns(m["recipient"]))
    if crossing:
        print(f"  - {name}: {len(groups)} namespaces but {crossing} edge(s) cross "
              f"them, so they are labels inside one population -- kept pooled")
        return {name: (log, meta)}

    print(f"  - {name}: {len(groups)} namespaces and no edge between any of them, "
          f"so this file is {len(groups)} separate graphs. Split; a centralization "
          f"over the union would be a number about the union")
    out = {}
    for g in groups:
        part = [m for m in log if ns(m["sender"]) == g]
        sub = dict(meta)
        sub["split_from"] = name
        sub["split_note"] = (
            f"one of {len(groups)} disconnected components in {name}, selected by "
            f"the id namespace '{g}'. Pooled figures for {name} are not reported "
            f"because the pooled graph is not a colony.")
        if isinstance(meta.get("special_nodes"), dict):
            sub["special_nodes"] = {k: v for k, v in meta["special_nodes"].items()
                                    if ns(k) == g}
        elif isinstance(meta.get("special_nodes"), (list, set, tuple)):
            sub["special_nodes"] = [k for k in meta["special_nodes"] if ns(k) == g]
        out[f"{name}[{g}]"] = (part, sub)
    return out


def find_stray_logs(root: Path) -> list:
    """Interaction logs sitting somewhere under the drive other than processed/.

    A loader run with `--out .../data/canonical/gernat_q` writes a perfectly good
    log that the bench will never glob. Rather than report an empty structure
    section and let it read as "no structure to report", look one level wider and
    name what was found.
    """
    if not root.exists():
        return []
    return sorted({p.parent.relative_to(root)
                   for p in root.glob("data/*/*/interaction_log.csv")
                   if p.parent.parent.name != "processed"})


def load_logs(root: Path) -> dict[str, tuple]:
    """Every interaction log under data/processed/, including nested ones.

    The Illinois loader writes one subdirectory per trial -- five independent
    colonies -- so this walks two levels rather than one. A flat scan would
    silently find nothing there and quietly drop the only replication we have.
    Gernat does the opposite: three colonies in one file, separated here.
    """
    out = {}
    proc = root / "data" / "processed"
    if not proc.exists():
        return out
    from loaders.gernat import read_log
    for path in sorted(proc.glob("*/interaction_log.csv")) + \
            sorted(proc.glob("*/*/interaction_log.csv")):
        d = path.parent
        name = d.name if d.parent == proc else f"{d.parent.name}/{d.name}"
        try:
            log, meta = read_log(d)
            out.update(split_if_disconnected(name, log, meta))
        except Exception as e:                          # noqa: BLE001
            print(f"  ! {name}: could not read interaction_log.csv ({e})")
    return out


def task_variation(events) -> tuple[float, int]:
    """Fraction of individuals that ever carry more than one task label.

    Computed from the events themselves rather than trusting `meta`, so it
    covers every row in the table -- loader output, synthetic rows, and anything
    added later.

    Why this exists. Charbonneau & Dornhaus publish `ClustDesc`, a behavioural
    cluster that turns out to be assigned ONCE per ant from the pooled record
    rather than per trial. Feed that in and every instrument here still returns a
    number, and every number is wrong in the same direction:

      * DoL is maximal by construction. Mutual information between individual
        and task is the entire entropy of the task variable when each individual
        maps to exactly one task, so normalized MI is 1.0 -- "perfect division of
        labour" that is an arithmetic restatement of "the label never changes".
      * Role stability kappa is exactly 1.0, for the same reason: the modal task
        in every window is the only task.
      * switch_fraction is structurally zero, so flexibility reports a colony
        that did not respond to the shock at all.

    None of that raises. It is the same failure as binding `time` to the column
    named `i`: a full set of plausible numbers about something that was never
    measured. So we detect it and refuse to report, rather than printing the
    numbers with a footnote nobody reads.
    """
    seen = defaultdict(set)
    for a, k, _t in events:
        seen[a].add(k)
    if not seen:
        return 0.0, 0
    multi = sum(1 for s in seen.values() if len(s) > 1)
    return multi / len(seen), len(seen)


def synthetic_rows(n_perm: int, n_boot: int) -> dict[str, tuple]:
    """Optional: the mechanistic systems from bench.py, as comparison rows."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import bench                                     # type: ignore
    except Exception:                                    # noqa: BLE001
        print("  (bench.py not importable here; skipping synthetic rows)")
        return {}
    out = {}
    for name, sysdef in bench.SYSTEMS:
        log = bench.run(sysdef, seed=3)
        events = [(i, k, t) for t, step in enumerate(log)
                  for i, k in enumerate(step) if k is not None]
        meta = dict(source="bench.py (synthetic)", shift_timestep=bench.SHIFT,
                    task_definition="designed task type")
        out["SYNTH " + name.strip()] = (events, meta)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="the BeeOrg project folder")
    ap.add_argument("--synthetic", action="store_true",
                    help="also run bench.py's mechanistic systems for comparison")
    ap.add_argument("--perm", type=int, default=50, help="permutations for the DoL null")
    ap.add_argument("--boot", type=int, default=200, help="bootstrap resamples")
    ap.add_argument("--windows", type=int, default=4, help="windows for role stability")
    ap.add_argument("--out", default=None, help="report path (default logs/real_bench.json)")
    a = ap.parse_args()

    root = Path(a.root).expanduser()
    datasets = load_processed(root)
    if a.synthetic:
        datasets.update(synthetic_rows(a.perm, a.boot))
    logs = load_logs(root)

    if not datasets and not logs:
        raise SystemExit("nothing to measure yet. Run the loaders first.")

    report: dict[str, dict] = {}

    # ------------------------------------------------- allocation instruments
    degenerate: dict[str, dict] = {}

    if datasets:
        print("\nDIVISION OF LABOUR  (raw, permutation null, bias-corrected, bootstrap CI)")
        print("-" * 100)
        for name, (events, meta) in datasets.items():
            if not events:
                print(f"{name:28} EMPTY")
                continue

            # Degeneracy check FIRST, before any instrument runs. If no
            # individual ever changes task label, the label is a static
            # attribute and not a behavioural state; DoL, kappa and
            # switch_fraction are then determined by that fact alone and carry
            # no information about the colony. Computing them anyway and
            # attaching a caveat is not enough -- a number in a table gets
            # quoted, and the caveat does not travel with it.
            varies, n_ind = task_variation(events)
            if n_ind > 1 and varies == 0.0:
                print(f"{name:28} DEGENERATE -- not measured "
                      f"({n_ind} individuals, none ever changes task)")
                info = dict(
                    degenerate=True,
                    n_individuals=n_ind,
                    task_varies_within_agent=0.0,
                    source=meta.get("source"),
                    task_definition=meta.get("task_definition"),
                    reason=("every individual carries exactly one task label for the "
                            "whole record, so the label is a static per-individual "
                            "attribute rather than a behavioural state. DoL would be "
                            "1.0, role-stability kappa exactly 1.0 and switch_fraction "
                            "exactly 0.0 by construction. Those are arithmetic "
                            "restatements of the labelling, not measurements, so they "
                            "are withheld rather than reported with a caveat."),
                    what_to_do=("re-run the loader with a task variable that varies "
                                "within individual over time -- for Charbonneau & "
                                "Dornhaus that is `--task-from activity`, which bins "
                                "the per-trial active-time proportion and must be "
                                "reported as a proxy. The static label is still useful "
                                "as a COVARIATE: do ants of different clusters respond "
                                "differently to the removal?"),
                )
                report[name] = info
                degenerate[name] = info
                continue

            rep = instruments.dol_report(events, a.perm, a.boot)
            print(instruments.summary_line(name, rep))
            rep["stability"] = instruments.role_stability(events, a.windows)
            shift = meta.get("shift_timestep")
            if shift is not None:
                rep["flexibility"] = instruments.flexibility_around_shock(events, int(shift))
            rep["source"] = meta.get("source")
            rep["task_definition"] = meta.get("task_definition")
            rep["task_varies_within_agent"] = round(varies, 4)
            if varies < 0.05:
                rep.setdefault("caveats", {})["low_task_variation"] = (
                    f"only {varies:.1%} of individuals ever change task label, so "
                    "specialization and stability are close to their structural "
                    "maxima and say little about the colony.")
            for caveat in ("task_caveat", "temporal_caveat", "shift_note"):
                if meta.get(caveat):
                    rep.setdefault("caveats", {})[caveat] = meta[caveat]
            report[name] = rep

        if degenerate:
            print("\nWITHHELD  (task label does not vary within individual)")
            print("-" * 100)
            for name, info in degenerate.items():
                print(f"{name:28} {info['task_definition'] or 'task'} is a static "
                      f"per-individual attribute here.")
                print(f"{'':28} DoL, kappa and switch_fraction would be 1.0, 1.0 and "
                      f"0.0 by construction.")
                print(f"{'':28} -> {info['what_to_do'].split(' -- ')[0]}")

        print("\nVERDICT vs. the permutation null")
        print("-" * 100)
        for name, rep in report.items():
            if rep.get("degenerate"):
                print(f"{name:28} WITHHELD (degenerate task labelling)")
                continue
            print(f"{name:28} {rep['verdict']}")

        print("\nROLE STABILITY  (does the same individual keep the same task?)")
        print("-" * 100)
        for name, rep in report.items():
            st = rep.get("stability", {})
            if st.get("agreement_mean") is None:
                continue
            print(f"{name:28} agreement={st['agreement_mean']:.3f} "
                  f"chance={st['chance_agreement']:.3f} kappa={st.get('kappa')}")

        flex_rows = {k: v["flexibility"] for k, v in report.items() if "flexibility" in v}
        if flex_rows:
            print("\nFLEXIBILITY AROUND A SHOCK")
            print("-" * 100)
            for name, fx in flex_rows.items():
                if fx.get("error"):
                    print(f"{name:28} {fx['error']}")
                    continue
                print(f"{name:28} response_tvd={fx['response_tvd']:.3f} "
                      f"switch_frac={fx.get('switch_fraction')} "
                      f"recovery_steps={fx.get('recovery_steps')}")
        else:
            print("\nFLEXIBILITY: no dataset carried a shock timestep. Charbonneau & "
                  "Dornhaus is the one that should -- process it first.")

    # ---------------------------------------------------- structure instruments
    if not logs:
        # A section that simply does not appear is the worst way to report a
        # missing input: the run succeeds, the summary is complete on its own
        # terms, and the reader concludes there was no structure to report rather
        # than that nothing was looked at. This happened on the real drive -- the
        # Gernat loader had been pointed at `data/canonical/gernat_q`, the bench
        # globs `data/processed/`, and the whole COMMUNICATION STRUCTURE block
        # silently vanished from the output.
        proc = root / "data" / "processed"
        strays = find_stray_logs(root)
        print("\nCOMMUNICATION STRUCTURE: nothing to read.")
        print("-" * 100)
        print(f"  looked for {proc}/*/interaction_log.csv and one level below it, "
              f"and found none.")
        if strays:
            print(f"  but there ARE interaction logs elsewhere under the drive: "
                  f"{', '.join(str(s) for s in strays)}")
            print(f"  -> re-run the loader with --out under data/processed/, or "
                  f"move those folders there. The bench does not follow a loader "
                  f"to wherever it was told to write.")
        else:
            print("  -> run loaders.gernat / loaders.illinois / loaders.mersch_net "
                  "with --out under data/processed/.")

    if logs:
        print("\nCOMMUNICATION STRUCTURE  (from directed interaction logs)")
        print("-" * 100)
        for name, (log, meta) in logs.items():
            rep = netstats.structure_report(log, k=10, n_perm=30,
                                            special=meta.get("special_nodes"))
            st = rep["stability"]
            print(f"{name:28} n={rep['n_individuals']:>5} "
                  f"centralization={rep['centralization']:.4f} "
                  f"(null {rep['centralization_null_mean']}, z={rep['centralization_z']}, "
                  f"{rep['events_per_unique_pair']} events per unique pair)")
            # The observed repetition never travels without the null's own. Read
            # against 1.0, an events_per_unique_pair of 1.2 says "no repetition";
            # read against the 1.03 a random re-assignment of the same event
            # counts gives, it says "twenty per cent narrower than chance", which
            # is the whole of the negative z.
            pn = rep.get("partner_narrowing") or {}
            if pn.get("narrowing") is not None:
                print(f"{'':28} partner sets {pn['narrowing']}x narrower than a "
                      f"random re-assignment of the same event counts "
                      f"(null repeats {pn['events_per_unique_pair_null']}x)")
            # Same discipline as the queen line below: the z and the reason it
            # cannot be read at face value are printed together, because a z of
            # -14.7 sitting alone on a line will be quoted as "significantly less
            # centralized than chance", which is not what it means.
            if rep.get("z_note"):
                for chunk in textwrap.wrap(rep["z_note"], 68):
                    print(f"{'':28} {chunk}")
            sp = rep.get("special_nodes")
            if sp and sp.get("join_failed"):
                print(f"{'':28} !! {sp['join_failed']}")
            elif sp and sp.get("n_present"):
                # Printed directly under the centralization figure on purpose:
                # the number and the caveat that qualifies it should not be able
                # to travel separately.
                rng_txt = (f"vs {sp['delta_null_range']} for the same number of "
                           f"arbitrary bees" if sp.get("delta_null_range")
                           else "no null available")
                print(f"{'':28} {sp['n_present']} queen(s) marked; without them "
                      f"centralization={sp['centralization_without']:.4f} "
                      f"({sp['delta']:+.4f}, {rng_txt}), top-{10} contains "
                      f"{len(sp['in_top_k'])} of them")
            if not st.get("error"):
                print(f"{'':28} hub Jaccard={st['jaccard_mean']:.3f} "
                      f"(chance {st['jaccard_chance']:.3f}), "
                      f"{st['persistent_hub_count']} persistent hubs")
            rep["source"] = meta.get("source")
            rep["directed"] = meta.get("directed")
            report[name + " [structure]"] = rep

        # The Illinois trials are five independent colonies measured identically,
        # so they are the one place we can ask whether a network result is a
        # property of colonies or of one colony. Spread across replicates is the
        # honest number; the mean alone would hide a two-of-five outcome.
        reps = {n: report[n + " [structure]"] for n in logs
                if n.startswith("illinois_portal/")}
        if len(reps) > 1:
            cen = sorted(r["centralization"] for r in reps.values())
            hubs = [r["stability"].get("persistent_hub_count")
                    for r in reps.values() if not r["stability"].get("error")]
            # Counted, but NOT described as "flatter than chance". The recipient
            # shuffle widens every partner set that is narrower than chance, which
            # raises the null's dmax, so a negative z is the default reading for a
            # colony and carries no information on its own -- see the z_note
            # printed above and test_null_calibration in selftest.py.
            below = sum(1 for r in reps.values() if (r.get("centralization_z") or 0) < 0)
            epup = sorted(r.get("events_per_unique_pair") or 0 for r in reps.values())
            narrow = sorted((r.get("partner_narrowing") or {}).get("narrowing") or 0
                            for r in reps.values())
            print(f"\nREPLICATION across {len(reps)} independent colonies")
            print("-" * 100)
            print(f"  centralization  min {cen[0]:.4f}  median {cen[len(cen) // 2]:.4f}  "
                  f"max {cen[-1]:.4f}")
            print(f"  z below zero in {below}/{len(reps)} colonies, at "
                  f"{epup[0]}-{epup[-1]} events per unique pair and "
                  f"{narrow[0]}-{narrow[-1]}x\n  narrower than chance -- which is "
                  f"what narrowed contact does to this null, not a finding of "
                  f"flatness. Quote the centralization spread.")
            if hubs:
                print(f"  persistent hubs per colony: {hubs}")
            print("  A result that holds in one of five is not a result. Quote the "
                  "spread, not the mean.")
            report["illinois_portal [replication]"] = dict(
                n_colonies=len(reps), centralization_sorted=cen,
                n_z_below_zero=below, events_per_unique_pair_sorted=epup,
                narrowing_sorted=narrow,
                persistent_hub_counts=hubs)

    out = Path(a.out) if a.out else root / "logs" / "real_bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nfull report -> {out}")

    print("""
How to read this
----------------
DoL_corr near zero with a low z means the colony's apparent division of labour
is a small-sample artifact. Only DoL_corr is quotable.

A row marked WITHHELD is not a failure of the data; it means the task variable
in that file never changes within an individual, so specialization and stability
are fixed by the labelling rather than measured. The numbers are omitted on
purpose. Give the loader a task variable that varies over time and the row comes
back.

High spec with high kappa = stable specialists. High spec with low kappa =
individuals specialize at any moment but the assignment churns, which is the
more interesting organizational case and the one that maps onto 'same algorithm,
different input, different output'.

For flexibility, response_tvd and switch_fraction should be read together: an
aggregate distribution that barely moves while half the individuals switch
tasks means the colony re-allocated WITHOUT changing its overall output mix.
That is the biological version of resilience, and no org chart encodes it.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
