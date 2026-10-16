"""Track the randomized-name rerun as specimens arrive, and mirror it to the drive.

    python3 -m diffenv.track_alias            # from code/, on the Mac or from the session

Reads diffenv_results/alias_rerun/{specimens,journal}, scores every finished run, compares
with the original (fixed-name) gpt runs in diffenv_results/final/specimens, writes STATUS.md
next to the specimens, and copies specimens, journals and STATUS.md to the drive if it is
mounted.  Safe to run at any time and as often as you like; it makes no API calls.

What it asks of each run, always against the label-permutation null (200 draws):
  work|opp     work actions per round in which the agent had something to work
  interaction  tells sent + received per window
  received     tells received per window          <- where the name preference showed
  sent|opp     tells sent per round with something in hand
and the label check: how many tells NAME each label (the model's preference) against how
many tells each REAL agent received (what the preference did to the organization).
"""
from __future__ import annotations

import glob, itertools, json, os, re, shutil, sys, time
from collections import Counter, defaultdict

import numpy as np

from .measures import differentiation, _spearman

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RERUN = os.path.join(HERE, "diffenv_results", "alias_rerun")
ORIG = os.path.join(HERE, "diffenv_results", "final", "specimens")
DRIVES = [p for p in os.environ.get("DIFFENV_MIRROR", "").split(os.pathsep) if p]  # optional backup copies
PLANNED = [f"c1+{f}private+alias-openai-gpt-4.1-mini-seed{s}" for f in ("", "exit+") for s in (0, 1, 2)]
MEASURES = ("work|opp", "interaction", "received", "sent|opp")


def tables(d):
    ag = d["agents"]; W = d["config"]["window"]; nW = d["config"]["rounds"] // W
    opp = {}
    for k, v in d["opportunity"].items():
        a, r = k.split("|"); opp[(a, int(r))] = v
    sent = defaultdict(int); rec = defaultdict(int); work = defaultdict(int)
    for m in d["log"]:
        w = m["window"]
        if m["mtype"] == "tell":
            sent[(m["sender"], w)] += 1; rec[(m["recipient"], w)] += 1
        elif m["mtype"] == "work":
            work[(m["sender"], w)] += 1
    T = defaultdict(list)
    for w in range(nW):
        for a in ag:
            o = sum(1 for r in range(w * W, (w + 1) * W) if opp.get((a, r), 0) > 0)
            T["interaction"].append(("r", w, a, sent[(a, w)] + rec[(a, w)]))
            T["received"].append(("r", w, a, rec[(a, w)]))
            if o > 0:
                T["sent|opp"].append(("r", w, a, sent[(a, w)] / o))
                T["work|opp"].append(("r", w, a, work[(a, w)] / o))
    return T


def score(path):
    d = json.load(open(path)); T = tables(d); ag = d["agents"]
    out = {"id": d["specimen_id"], "agents": ag, "done": d["outcome"]["completed"], "left": d["outcome"]["agents_left"],
           "actions": dict(Counter(m["mtype"] for m in d["log"])), "cost": (d.get("usage_this_run") or {}).get("cost_usd", 0),
           "unparseable": (d.get("llm") or {}).get("unparseable"), "alias": bool((d.get("llm") or {}).get("alias")),
           "written": d.get("written")}
    for k in MEASURES:
        r = differentiation(T[k], seed=0, n_draws=200)["R"]
        out[k] = (r["observed"], r["null_p95"])
    rec = Counter(m["recipient"] for m in d["log"] if m["mtype"] == "tell")
    sent = Counter(m["sender"] for m in d["log"] if m["mtype"] == "tell")
    out["received_by_agent"] = [rec[a] for a in ag]; out["sent_by_agent"] = [sent[a] for a in ag]
    named = Counter()
    for r in d.get("raw_replies") or []:
        m = re.match(r"\s*tell\b.*?\b(A\d+)\b", r["reply"], re.I)
        if m:
            named[m.group(1).upper()] += 1
    out["named_by_label"] = [named[a] for a in ag]
    return out


def cell(x):
    o, n = x
    return f"{o:.2f}{' **above**' if o > n else ''} ({n:.2f})"


def cross_run(runs, key):
    if len(runs) < 2:
        return None
    c = [_spearman(a[key], b[key]) for a, b in itertools.combinations(runs, 2)]
    return float(np.mean(c)), float(min(c)), len(c)


def main():
    os.makedirs(os.path.join(RERUN, "specimens"), exist_ok=True)
    new = [score(p) for p in sorted(glob.glob(os.path.join(RERUN, "specimens", "*.json")))]
    old = [score(p) for pat in ("c1+private-openai-gpt-4.1-mini-seed*.json", "c1+exit+private-openai-gpt-4.1-mini-seed*.json")
           for p in sorted(glob.glob(os.path.join(ORIG, pat)))]
    done_ids = {r["id"] for r in new}
    L = [f"# Randomized-name rerun — status {time.strftime('%Y-%m-%d %H:%M:%S')}", "",
         f"{len(done_ids & set(PLANNED))} of {len(PLANNED)} planned runs complete. "
         f"Spent so far: ${sum(r['cost'] for r in new):.2f}.", "", "## Progress", "",
         "| run | state | items done (of 600) | work / tell / pass | agents left |", "|---|---|---|---|---|"]
    by_id = {r["id"]: r for r in new}
    for pid in PLANNED + sorted(done_ids - set(PLANNED)):
        if pid in by_id:
            r = by_id[pid]; a = r["actions"]
            L.append(f"| {pid} | complete {r['written']} | {r['done']} | {a.get('work',0)} / {a.get('tell',0)} / {a.get('pass',0)} | {len(r['left'])} |")
        else:
            j = os.path.join(RERUN, "journal", pid + ".jsonl")
            n = sum(1 for _ in open(j)) if os.path.isfile(j) else 0
            L.append(f"| {pid} | {'running' if n else 'not started'}: {n} of 900 calls | | | |")
    L += ["", "## Repeatability, observed (null 95th percentile)", "",
          "| run | names | " + " | ".join(MEASURES) + " |", "|---|---|" + "---|" * len(MEASURES)]
    for r in old:
        L.append(f"| {r['id']} | fixed | " + " | ".join(cell(r[k]) for k in MEASURES) + " |")
    for r in new:
        L.append(f"| {r['id']} | randomized | " + " | ".join(cell(r[k]) for k in MEASURES) + " |")
    L += ["", "## Label check", "",
          "`named` = tells in which the model wrote each label A0..A8 (its name preference). "
          "`received` = tells each real agent A0..A8 actually received.", "",
          "| run | named, by label | received, by real agent | max / min received |", "|---|---|---|---|"]
    for r in old + new:
        rec = r["received_by_agent"]
        L.append(f"| {r['id']} | {r['named_by_label']} | {rec} | {max(rec)} / {min(rec)} |")
    L += ["", "## Does the same agent come out on top in every run?", ""]
    for name, runs, key in (("fixed names, received by agent", old, "received_by_agent"),
                            ("randomized names, received by real agent", new, "received_by_agent"),
                            ("randomized names, named by label", new, "named_by_label")):
        c = cross_run(runs, key)
        L.append(f"- {name}: " + (f"mean cross-run rank correlation {c[0]:+.2f} (min {c[1]:+.2f}, {c[2]} pairs)" if c else "needs two runs"))
    if new:
        above = {k: sum(1 for r in new if r[k][0] > r[k][1]) for k in MEASURES}
        L += ["", "## Reading so far", "",
              "Runs above their null, randomized names: " + ", ".join(f"{k} {v}/{len(new)}" for k, v in above.items()) + ".",
              "Fixed names, for comparison: " + ", ".join(f"{k} {sum(1 for r in old if r[k][0] > r[k][1])}/{len(old)}" for k in MEASURES) + ".",
              "With 200 permutation draws, about 1 run in 20 exceeds its null by chance on any one measure."]
    text = "\n".join(L) + "\n"
    open(os.path.join(RERUN, "STATUS.md"), "w").write(text)
    mirrored = None
    for d in DRIVES:
        if os.path.isdir(d):
            dst = os.path.join(d, "alias_rerun")
            for sub in ("specimens", "journal"):
                os.makedirs(os.path.join(dst, sub), exist_ok=True)
                for f in glob.glob(os.path.join(RERUN, sub, "*")):
                    shutil.copy2(f, os.path.join(dst, sub))
            shutil.copy2(os.path.join(RERUN, "STATUS.md"), dst)
            mirrored = dst
            break
    print(text)
    print("mirrored to drive:", mirrored or "DRIVE NOT MOUNTED — results are in the project folder only", file=sys.stderr)


if __name__ == "__main__":
    main()
