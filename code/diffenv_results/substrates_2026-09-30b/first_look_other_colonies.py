"""First look, 30 September 2026: can the other colony deposits be scored on the same
`interaction` construct as the clonal ants and the office workers?  Run from code/:

    PYTHONPATH=. python3 diffenv_results/substrates_2026-09-30b/first_look_other_colonies.py <BeeOrg/data/raw>

Mersch, Crespi & Keller 2013 (Camponotus fellah, 6 colonies x 41 days): per ant per day, the
row sum of the daily interaction matrix (number of interactions).  Queen NOT removed in this
pass (one ant in 100-190).  Ants are of mixed age and known task group - not exchangeable.
Gernat et al. 2018 (honey bees, 3 colonies x 5 days): per bee per day, the number of
trophallaxis events it took part in; queen removed; days after a bee's recorded death dropped.
Same rules as the human leg: no interaction on a day = absent that day; keep individuals
present on >= 4 days.  Also: the office data re-scored in random pools of 7 (the ant pool size).
"""
import csv, glob, json, os, random, re, sys
from collections import defaultdict
import numpy as np
from diffenv.measures import differentiation
from diffenv.substrates import invs_tables

RAW = sys.argv[1]; out = {}
def keep(table, min_w=4):
    n = defaultdict(int)
    for o, w, a, v in table: n[(o, a)] += 1
    return [r for r in table if n[(r[0], r[2])] >= min_w]
def score(name, table, draws=200):
    d = differentiation(table, seed=0, n_draws=draws)
    pools = defaultdict(int)
    for o, w, a, v in table: pools[(o, w)] += 1
    out[name] = {"R": d["R"], "split_half": d["split_half"], "n_agents": d["n_agents"], "n_org_windows": d["n_windows"],
                 "median_pool": float(np.median(list(pools.values())))}
    print(f"{name:34} R {d['R']['observed']:.3f} (null p95 {d['R']['null_p95']:.3f}) split-half {d['split_half']['observed']:+.3f} | agents {d['n_agents']} org-windows {d['n_windows']} median pool {np.median(list(pools.values())):.0f}", flush=True)

# ---- Mersch
tab = []
for f in sorted(glob.glob(os.path.join(RAW, "mersch_keller_2013/tracking_data/network_col*_day*.txt"))):
    m = re.search(r"network_col(\d+)_day(\d+)", f); col, day = f"col{m.group(1)}", int(m.group(2))
    L = open(f).read().strip().splitlines(); ids = L[0].split(",")
    M = np.array([[float(x) for x in l.split(",")] for l in L[1:]])
    assert M.shape == (len(ids), len(ids))
    rs = M.sum(1) - np.diag(M)
    tab += [(col, day, f"{col}:{i}", float(v)) for i, v in zip(ids, rs) if v > 0]
score("Mersch ants, interactions/day", keep(tab))
# first 11 days only (period 1), to see whether mortality over 41 days drives it
score("Mersch ants, days 1-11 only", keep([r for r in tab if r[1] <= 11]))

# ---- Gernat
R = os.path.join(RAW, "gernat_trophallaxis")
begin = {r["trial"]: int(r["begin"]) for r in csv.DictReader(open(os.path.join(R, "trials.csv")))}
queen = set(); death = {}
for r in csv.DictReader(open(os.path.join(R, "bees.csv"))):
    if r["caste"] != "worker": queen.add((r["trial"], r["id"]))
    death[(r["trial"], r["id"])] = int(r["time_of_death"]) if r["time_of_death"] else None
cnt = defaultdict(int)
for r in csv.DictReader(open(os.path.join(R, "interactions.csv"))):
    t = int(r["timestamp"]); d = (t - begin[r["trial"]]) // 86400
    for b in (r["id1"], r["id2"]):
        k = (r["trial"], b)
        if k in queen: continue
        if death.get(k) is not None and death[k] < t: continue
        cnt[(r["trial"], d, b)] += 1
tab = [(tr, d, f"{tr}:{b}", float(v)) for (tr, d, b), v in cnt.items()]
print("gernat days per trial:", {tr: sorted({d for t2, d, _, _ in tab if t2 == tr}) for tr in begin})
tab = [r for r in tab if r[1] <= 4]          # five full days; drop the partial last bin if any
score("Gernat bees, trophallaxis/day", keep(tab))

# ---- office workers in pools of 7
rng = random.Random(0)
for yr, tij, meta in (("2013", "sociopatterns_workplace_2013/tij_InVS.dat", "sociopatterns_workplace_2013/workplace_InVS_metadata.txt"),
                      ("2015", "sociopatterns_workplace_2015/workplace_InVS15_tij.dat.gz", "sociopatterns_workplace_2015/workplace_InVS15_metadata.txt")):
    h = invs_tables(os.path.join(RAW, tij), os.path.join(RAW, meta), org=f"InVS{yr}", min_days=4)
    people = sorted({a for _, _, a, _ in h["interaction"]}); Rs = []; nulls = []
    for rep in range(20):
        rng.shuffle(people); grp = {p: i // 7 for i, p in enumerate(people)}
        sizes = defaultdict(int)
        for p in people: sizes[grp[p]] += 1
        t = [(f"g{grp[a]}", w, a, v) for _, w, a, v in h["interaction"] if sizes[grp[a]] == 7]
        d = differentiation(t, seed=rep, n_draws=40)["R"]; Rs.append(d["observed"]); nulls.append(d["null_p95"])
    out[f"InVS{yr}_pools_of_7"] = {"R_mean": float(np.mean(Rs)), "R_min": float(min(Rs)), "R_max": float(max(Rs)), "null_p95_mean": float(np.mean(nulls)), "partitions": 20}
    print(f"InVS{yr} in random pools of 7        R mean {np.mean(Rs):.3f} (range {min(Rs):.3f}-{max(Rs):.3f}; null p95 ~{np.mean(nulls):.3f}) over 20 partitions", flush=True)
    dep = h["department"]
    t = [(f"dept{dep.get(a,'?')}", w, a, v) for _, w, a, v in h["interaction"]]
    score(f"InVS{yr} within department", t, draws=100)
json.dump(out, open(os.path.join(os.path.dirname(__file__), "first_look_other_colonies.json"), "w"), indent=1)
