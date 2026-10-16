"""Cross-system labor-allocation bench.

One environment, one set of measurement instruments, applied to BOTH a
biologically grounded insect colony and several human-organizational designs.
Every system allocates a workforce across K task types whose demand SHIFTS
midway, and we score each with the SAME instruments:

  * DoL      — division of labor (normalized mutual information agent<->task)
  * spec     — mean per-agent specialization
  * flex     — flexibility: how well labor re-matches demand AFTER the shift

The point is not the specific numbers but that biological and organizational
labor allocation become comparable in one measurement space. Everything is
mechanistic (no LLM), so results cannot be an artifact of model priors.
"""
import random, math

N = 48          # agents
K = 4           # task types
T = 240         # timesteps
SHIFT = 120     # demand shift happens here
DEMAND_PRE  = [0.40, 0.40, 0.10, 0.10]
DEMAND_POST = [0.10, 0.10, 0.40, 0.40]


def demand(t):
    return DEMAND_PRE if t < SHIFT else DEMAND_POST


# ---------- shared environment ----------
def new_stimuli():
    return [0.0] * K

def influx(t):
    d = demand(t)
    return [d[k] * N for k in range(K)]   # work units arriving per step

def apply_work(stim, counts, t):
    inf = influx(t)
    for k in range(K):
        stim[k] = max(0.0, stim[k] + inf[k] - counts[k])  # each worker clears 1 unit


# ---------- systems: each returns a per-step list of chosen task (or None) ----------
def run(system, seed=0):
    rng = random.Random(seed)
    stim = new_stimuli()
    log = []                       # log[t][i] = task or None
    state = system["init"](rng)
    for t in range(T):
        choices = system["step"](state, stim, t, rng)
        counts = [0] * K
        for k in choices:
            if k is not None:
                counts[k] += 1
        apply_work(stim, counts, t)
        log.append(choices)
    return log


def colony_from_events(events):
    """Load a REAL insect colony from tracked interaction/task events.

    `events` is an iterable of (agent_id, task_id, timestep). This is the drop-in
    point for real social-insect data (e.g., barcode/computer-vision tracking such
    as Gernat et al. 2023, or the Animal Social Network Repository). The returned
    log has the same shape the mechanistic systems produce, so the identical
    measurement instruments (dol_and_spec, flexibility) apply unchanged.
    """
    agents = sorted({a for a, _, _ in events})
    idx = {a: i for i, a in enumerate(agents)}
    tmax = max((t for _, _, t in events), default=-1)
    log = [[None] * len(agents) for _ in range(tmax + 1)]
    for a, k, t in events:
        log[t][idx[a]] = k
    return log


# colony: response-threshold division of labor (Bonabeau/Theraulaz/Deneubourg)
def colony(hetero=True):
    def init(rng):
        theta = []
        for i in range(N):
            if hetero:
                pref = i % K                      # each agent has a low-threshold task
                th = [rng.uniform(6, 10) for _ in range(K)]
                th[pref] = rng.uniform(0.5, 2.0)
            else:
                th = [4.0 for _ in range(K)]       # identical agents -> no specialization
            theta.append(th)
        return {"theta": theta}
    def step(state, stim, t, rng):
        theta = state["theta"]
        out = []
        for i in range(N):
            probs = [ (stim[k]**2) / (stim[k]**2 + theta[i][k]**2 + 1e-9) for k in range(K) ]
            k = max(range(K), key=lambda k: probs[k])
            out.append(k if rng.random() < probs[k] else None)
        return out
    return {"init": init, "step": step}


# functional silos: fixed partition sized to PRE-shift demand (optimized for t<SHIFT)
def silos():
    def init(rng):
        assign = []
        for k in range(K):
            assign += [k] * round(DEMAND_PRE[k] * N)
        while len(assign) < N: assign.append(K - 1)
        assign = assign[:N]
        return {"assign": assign}
    def step(state, stim, t, rng):
        return [k if stim[k] > 0 else None for k in state["assign"]]
    return {"init": init, "step": step}


# centralized hierarchy: manager re-plans allocation to demand every L steps (lag)
def hierarchy(L=20):
    def init(rng):
        return {"plan": None, "last": -10**9}
    def replan(t):
        d = demand(t)
        assign = []
        for k in range(K):
            assign += [k] * round(d[k] * N)
        while len(assign) < N: assign.append(K - 1)
        return assign[:N]
    def step(state, stim, t, rng):
        if t - state["last"] >= L:
            state["plan"] = replan(t); state["last"] = t
        return [k if stim[k] > 0 else None for k in state["plan"]]
    return {"init": init, "step": step}


# flat self-organizing: each agent chases the highest-stimulus task (local info)
def flat():
    def init(rng): return {}
    def step(state, stim, t, rng):
        tot = sum(stim) + 1e-9
        out = []
        for i in range(N):
            if tot < 1e-6:
                out.append(None); continue
            r = rng.random() * tot; c = 0.0; pick = 0
            for k in range(K):
                c += stim[k]
                if r <= c: pick = k; break
            out.append(pick)
        return out
    return {"init": init, "step": step}


# ---------- shared instruments ----------
def dol_and_spec(log):
    C = [[0]*K for _ in range(N)]
    for step in log:
        for i, k in enumerate(step):
            if k is not None: C[i][k] += 1
    tot = sum(sum(r) for r in C) + 1e-9
    pk = [sum(C[i][k] for i in range(N))/tot for k in range(K)]
    pi = [sum(C[i])/tot for i in range(N)]
    mi = 0.0
    for i in range(N):
        for k in range(K):
            pik = C[i][k]/tot
            if pik > 0:
                mi += pik*math.log(pik/(pi[i]*pk[k]+1e-12)+1e-12)
    Hk = -sum(p*math.log(p+1e-12) for p in pk if p>0)
    dol = mi/Hk if Hk>0 else 0.0
    specs = []
    for i in range(N):
        s = sum(C[i])
        if s == 0: continue
        p = [C[i][k]/s for k in range(K)]
        H = -sum(x*math.log(x+1e-12) for x in p if x>0)
        specs.append(1 - H/math.log(K))
    spec = sum(specs)/len(specs) if specs else 0.0
    return max(0.0,min(1.0,dol)), spec

def match_window(log, lo, hi):
    vals = []
    for t in range(lo, hi):
        counts=[0]*K; act=0
        for k in log[t]:
            if k is not None: counts[k]+=1; act+=1
        if act==0: continue
        alloc=[counts[k]/act for k in range(K)]
        d=demand(t)
        vals.append(1 - 0.5*sum(abs(alloc[k]-d[k]) for k in range(K)))
    return sum(vals)/len(vals) if vals else 0.0

def flexibility(log):
    # settled demand-matching AFTER the shift (skip a 20-step transient)
    return match_window(log, SHIFT+20, T)

def pre_match(log):
    return match_window(log, SHIFT-60, SHIFT)


SYSTEMS = [
    ("colony (hetero)  [BIOLOGY]", colony(hetero=True)),
    ("colony (homo)    [control]", colony(hetero=False)),
    ("org: silos",                 silos()),
    ("org: hierarchy",             hierarchy()),
    ("org: flat",                  flat()),
]

def main():
    print(f"{'system':28} {'DoL':>5} {'spec':>5} {'pre-match':>9} {'flex(post)':>10}")
    rows=[]
    for name, sysdef in SYSTEMS:
        log = run(sysdef, seed=3)
        dol, spec = dol_and_spec(log)
        pm = pre_match(log); fx = flexibility(log)
        rows.append((name,dol,spec,pm,fx))
        print(f"{name:28} {dol:5.2f} {spec:5.2f} {pm:9.2f} {fx:10.2f}")
    print("\nReading: DoL/spec = how specialized; flex = how well labor re-matches")
    print("demand after it shifts. The biological colony is the benchmark; each org")
    print("design occupies a different point in the same specialization x flexibility space.")
    return rows

if __name__ == "__main__":
    main()
