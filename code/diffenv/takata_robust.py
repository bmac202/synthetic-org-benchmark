"""Takata robustness: 20-step windows, and R in steps 1-50 vs 51-100. Run from code/: python3 diffenv/takata_robust.py"""
import sys; sys.path.insert(0, ".")
import os
from diffenv.external import takata_tables
from diffenv.measures import differentiation
tidy=os.path.join("..","data","takata","tidy")
for rng in (0,5,10,25):
    t10=takata_tables(tidy,window=10,ranges=[rng]); t20=takata_tables(tidy,window=20,ranges=[rng])
    for k in ("move_rate","msg_len","mem_len"):
        d20=differentiation(t20[k],n_draws=100)
        e=differentiation([r for r in t10[k] if r[1]<5],n_draws=100); l=differentiation([r for r in t10[k] if r[1]>=5],n_draws=100)
        print(f"range {rng:2d} {k:<9} R(20-step windows)={d20['R']['observed']:.2f} (p95 {d20['R']['null_p95']:.2f}) | steps 1-50 R={e['R']['observed']:.2f} (p95 {e['R']['null_p95']:.2f}) | steps 51-100 R={l['R']['observed']:.2f} (p95 {l['R']['null_p95']:.2f})",flush=True)
