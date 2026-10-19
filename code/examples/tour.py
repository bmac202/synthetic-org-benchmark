"""A two-minute tour of structure-provenance analysis. No API key, no data download, no network.

    cd code
    python3 examples/tour.py            # 5 runs per condition, about 2 minutes
    python3 examples/tour.py --quick    # 3 runs per condition, about 1 minute

The tour uses rule-based agents whose source of differentiation is known, in the same
environment as the LLM runs (nine agents, a shared queue, 100 rounds, 10-round windows). It
answers the framework's three questions in turn and shows the evidence each one needs:

  1. Is there structure?        persistence above a shuffled baseline
  2. Is it robust?              survival under a design perturbation (balanced label shuffle)
  3. Where did it come from?    an intervention (wiping histories at mid-run)

It then writes three runs of each arm of question 2 as CSV logs in the documented format, so you
can see the same contrast through the one-command report:

    python3 provenance_report.py --csv examples/tour_fixed_names.csv
    python3 provenance_report.py --csv examples/tour_balanced_labels.csv

Replace that file with your own log (same columns) to analyze your own simulation or group.
The full known-answer test (ten conditions x 20 runs) is `python3 -m diffenv.ground_truth`.
"""
from __future__ import annotations

import argparse, csv, os, sys, time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # make `diffenv` importable from code/examples

from diffenv.env import OpenQueueEnv, default_config   # noqa: E402
from diffenv.ground_truth import CONDITIONS, run_condition, _pooled_continuity, contrasts   # noqa: E402

TOUR = ["none", "prescribed", "generated",                 # question 1
        "label", "label_balanced",                         # question 2
        "generated_wiped", "prescribed_random", "prescribed_random_wiped"]   # question 3


def above(cell):
    return cell["observed"] > cell["null_p95"]


def line(label, runs, key, what):
    obs = [r[key]["observed"] for r in runs]; base = [r[key]["null_p95"] for r in runs]
    k = sum(above(r[key]) for r in runs)
    return f"  {label:<44} {what} {np.median(obs):.2f} vs baseline {np.median(base):.2f}   above in {k} of {len(runs)} runs"


def cont_line(label, runs):
    c = _pooled_continuity(runs)
    return (f"  {label:<44} {c['observed']:.2f} of agents keep their favorite (chance {c['null_mean']:.2f}; "
            + ("p < 0.001)" if c["p_value"] < 0.001 else f"p = {c['p_value']:.3f})"))


def export_csv(path, cond, seeds=(0, 1, 2)):
    """Write runs of one condition in the documented log format (see provenance_report.py)."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run", "time", "member", "action", "partner", "task_type", "opportunity"])
        for seed in seeds:
            cfg = default_config(visibility="private")
            env = OpenQueueEnv(cfg, seed)
            env.run(CONDITIONS[cond][1](seed, env.agents, cfg.n_types))
            run = f"{cond}_seed{seed}"
            for (a, t), o in sorted(env.opportunity.items(), key=lambda x: (x[0][1], x[0][0])):
                if o:
                    w.writerow([run, t, a, "opp", "", "", 1])
            for m in env.log:
                if m["mtype"] == "work":
                    w.writerow([run, m["round"], m["sender"], "work", "", m["payload"].get("type") or "", ""])
                elif m["mtype"] == "tell":
                    w.writerow([run, m["round"], m["sender"], "tell", m["recipient"], "", ""])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="3 runs per condition instead of 5")
    a = ap.parse_args()
    n = 3 if a.quick else 5
    t0 = time.time()
    print(f"Structure-provenance tour: rule-based agents with known sources of differentiation, {n} runs per condition.")
    print("Each value is repeatability R (the share of between-member differences that persists across windows),")
    print("read against the 95th percentile of its own label-permutation null. Simulating", end="", flush=True)
    res = {}
    for c in TOUR:
        res[c] = [run_condition(c, s, 200) for s in range(n)]
        print(".", end="", flush=True)
    print(f" done in {time.time() - t0:.0f} s.\n")

    print("1. IS THERE STRUCTURE?  Does task specialization persist beyond chance?")
    print(line("No source (identical agents)", res["none"], "task_type", "task-type R"))
    print(line("Specialties prescribed in the agents' rules", res["prescribed"], "task_type", "task-type R"))
    print(line("Specialties learned from own history", res["generated"], "task_type", "task-type R"))
    print("  -> The measure stays at chance when there is nothing to find and detects both real sources.")
    print("     But both sources look alike here: persistence alone cannot say where structure came from.\n")

    print("2. IS IT ROBUST?  Agents prefer whoever carries the label 'A1'. Does the hub survive relabeling?")
    print(line("Fixed names", res["label"], "hub", "hub R      "))
    print(line("Balanced label shuffle", res["label_balanced"], "hub", "hub R      "))
    print("  -> A persistent communication hub that disappears when labels are balanced was produced by the")
    print("     design (a label cue), not by an organizing process among the agents.\n")

    print("3. WHERE DID IT COME FROM?  Wipe every agent's history at round 50, then ask whether agents keep their")
    print("   favorite task type across round 50 (all agents of all runs pooled; chance = favorites permuted).")
    print(cont_line("Learned, no wipe", res["generated"]))
    print(cont_line("Learned, history wiped", res["generated_wiped"]))
    print(cont_line("Prescribed (reassigned each run), no wipe", res["prescribed_random"]))
    print(cont_line("Prescribed (reassigned each run), wiped", res["prescribed_random_wiped"]))
    for lab, c in contrasts(res).items():
        name = "prescribed" if "prescribed" in lab else "learned"
        print(f"  Drop in continuity caused by the wipe, {name:<10} (paired by seed): {c['mean_difference']:.2f} "
              f"[95% CI {c['ci95'][0]:.2f}, {c['ci95'][1]:.2f}]")
    print("  -> The wipe returns history-dependent continuity toward chance but leaves prescribed roles intact:")
    print("     an intervention separates two sources that persistence alone could not.\n")

    export_csv(os.path.join(HERE, "tour_fixed_names.csv"), "label")
    export_csv(os.path.join(HERE, "tour_balanced_labels.csv"), "label_balanced")
    print("NEXT: the same robustness check through the one-command report. The tour wrote three runs of each")
    print("arm of question 2 as CSV logs in the documented format. Run the report on each and compare:")
    print("    python3 provenance_report.py --csv examples/tour_fixed_names.csv")
    print("    python3 provenance_report.py --csv examples/tour_balanced_labels.csv")
    print("The 'structural' (hub) column is above baseline in every fixed-name run, with the same member on top,")
    print("and at chance under balanced labels. The 'relational' column can stay above baseline in both: agents")
    print("still pair by label position, which is why the analysis package adds a label-aware partner baseline.")
    print("To analyze your own simulation or group, write a CSV with the same columns (run, time, member, action,")
    print("partner, task_type, optional opportunity) and pass it with --csv; `provenance_report.py --help` documents it.")


if __name__ == "__main__":
    main()
