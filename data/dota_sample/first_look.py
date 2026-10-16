"""First look at role persistence in the DOTA2 sample (player_matches.csv from get_dota_sample.py).
Free-pick matches only (game_mode 1 All Pick, 22 Ranked All Pick; lobby public or ranked).
Role = carry vs support, using heroes labelled only one of the two. For players with >= MIN such
matches: split each player's matches in time order into halves, correlate their carry shares
(split-half r, Spearman-Brown corrected), and compare with a baseline that shuffles role labels
across players (keeps every player's match count, destroys identity)."""
import sys, numpy as np, pandas as pd
MIN = int(sys.argv[1]) if len(sys.argv) > 1 else 20
rng = np.random.default_rng(0)
d = pd.read_csv("out/player_matches.csv")
n0 = len(d)
d = d[d.game_mode.isin([1, 22]) & d.lobby_type.isin([0, 7]) & d.role_class.isin(["carry", "support"])]
d = d.sort_values(["account_id", "start_time"])
d["carry"] = (d.role_class == "carry").astype(int)
k = d.groupby("account_id").carry.transform("size")
d = d[k >= MIN].copy()
def split_half(df):
    df = df.copy()
    pos = df.groupby("account_id").cumcount(); size = df.groupby("account_id").carry.transform("size")
    df["half"] = (pos >= size / 2).astype(int)
    s = df.groupby(["account_id", "half"]).carry.mean().unstack()
    r = s[0].corr(s[1]); return r, 2 * r / (1 + r)
r, sb = split_half(d)
null = []
for _ in range(200):
    e = d.copy(); e["carry"] = rng.permutation(e.carry.values); null.append(split_half(e)[0])
acc = d.groupby("account_id").agg(n=("carry", "size"), carry=("carry", "mean"),
                                   span=("start_time", lambda t: (t.max() - t.min()) / 86400),
                                   heroes=("hero_id", "nunique"))
top = d.groupby(["account_id", "hero_id"]).size().groupby("account_id").max() / acc.n
print(f"rows {n0:,} -> free-pick carry/support rows {len(d):,} for {len(acc):,} players with >= {MIN}")
print(f"matches per player: median {acc.n.median():.0f}, max {acc.n.max()}; time span median {acc.span.median():.0f} days")
print(f"overall carry share {d.carry.mean():.2f}; player carry share sd {acc.carry.std():.2f} "
      f"(binomial sd expected {np.sqrt((d.carry.mean()*(1-d.carry.mean())/acc.n)).mean():.2f})")
print(f"share of players >= 80% carry {(acc.carry >= .8).mean():.0%}, <= 20% carry {(acc.carry <= .2).mean():.0%}")
print(f"split-half r = {r:.2f}  (Spearman-Brown {sb:.2f});  shuffled baseline: mean {np.mean(null):.2f}, 95th pct {np.percentile(null, 95):.2f}")
print(f"most-played hero share: median {top.median():.0%}; distinct heroes median {acc.heroes.median():.0f}")
