"""Figure 1 (v5, 27 Oct 2026: rows of panel A named by species, "learned" -> "acquired" in panel B, after B. Baer's comments; otherwise v4 of 17/19 Oct 2026): three kinds of evidence.

A  Beyond our simulations: real groups against their own baselines
   (diffenv_results/substrates_*, external_2026-10-06; one marker per site).
B  When the answer is known: rule-based response-threshold agents, 20 runs per condition
   (diffenv_results/ground_truth_2026-10-17b/ground_truth.json).
C  LLM organizations: the confirmatory comparisons of ANALYSIS_PLAN_2026-10-16.md, 10 runs per
   cell (diffenv_results/plan_scores_2026-10-17/scores.json).

Grey bar: 0 to the row's median shuffled baseline (95th percentile of the label-permutation
null). Markers: one per run or site; filled if above its own baseline, hollow if not.
Black tick and line: median across runs with a bootstrap 95% interval (rows with >= 10 runs).
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "diffenv_results")
GT = json.load(open(os.path.join(RES, "ground_truth_2026-10-17b", "ground_truth.json")))["runs"]
PS = json.load(open(os.path.join(RES, "plan_scores_2026-10-17", "scores.json")))["runs"]

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, BAND = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#dcdbd5"
STYLE = {"real": (BLUE, "o"), "rule": (AQUA, "s"), "llm": (ORANGE, "^")}

def gt(cond, m): return [(r[m]["observed"], r[m]["null_p95"]) for r in GT[cond]]
def ps(cell, m): return [tuple(r[m]) for r in PS[cell]]

PANELS = [
    ("A  Does it work beyond our simulations?", "Real groups, each against its own baseline (one marker per site)", [
        ("Clonal raider ants", "time near nestmates", [(0.68, 0.13)], "real"),
        ("Carpenter ants", "interactions (first look)", [(0.56, 0.04)], "real"),
        ("Online game players", "carry vs support role", [(0.51, 0.15)], "real"),
        ("Honey bees", "food exchanges (first look)", [(0.43, 0.18)], "real"),
        ("Office workers, two sites", "face-to-face contacts", [(0.34, 0.16), (0.28, 0.14)], "real")]),
    ("B  Does it give the right answer when the answer is known?", "Rule-based agents with a known source of differences, 20 runs each", [
        ("No source", "task type", gt("none", "task_type"), "rule"),
        ("Specialties prescribed", "task type", gt("prescribed", "task_type"), "rule"),
        ("Specialties acquired from own history", "task type", gt("generated", "task_type"), "rule"),
        ("Acquired, histories wiped at mid-run", "task type", gt("generated_wiped", "task_type"), "rule"),
        ("Built-in preference for label “A1”", "message hub, fixed names", gt("label", "hub"), "rule"),
        ("Same, original label shuffle", "message hub", gt("label_shuffled", "hub"), "rule"),
        ("Same, balanced label shuffle", "message hub", gt("label_balanced", "hub"), "rule")]),
    ("C  Does it change how we read LLM organizations?", "Nine identical agents per run, 10 runs per row (pre-specified comparisons)", [
        ("gpt-4.1-mini, fixed names", "message hub", ps("gpt_fixed", "hub"), "llm"),
        ("gpt-4.1-mini, original label shuffle", "message hub", ps("gpt_latin", "hub"), "llm"),
        ("gpt-4.1-mini, balanced label shuffle", "message hub", ps("gpt_balanced", "hub"), "llm"),
        ("Nothing assigned, gpt-4.1-mini", "task type", ps("gpt_latin", "task"), "llm"),
        ("Nothing assigned, Haiku 4.5", "task type", ps("haiku_latin", "task"), "llm"),
        ("Told a specialty, gpt-4.1-mini", "task type", ps("gpt_assigned", "task"), "llm"),
        ("Told a specialty, Haiku 4.5", "task type", ps("haiku_assigned", "task"), "llm")]),
]

def boot_ci(v, n=10000, seed=1):
    rng = np.random.default_rng(seed); v = np.asarray(v)
    m = np.median(rng.choice(v, size=(n, len(v)), replace=True), axis=1)
    return np.percentile(m, 2.5), np.percentile(m, 97.5)

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"], "mathtext.fontset": "stix", "font.size": 10.0, "axes.edgecolor": MUTED,
                     "axes.linewidth": 0.6, "xtick.color": INK2, "ytick.color": INK2,
                     "pdf.fonttype": 42, "svg.fonttype": "none"})
heights = [len(p[2]) + 1.0 for p in PANELS]
fig, axes = plt.subplots(len(PANELS), 1, figsize=(6.5, 7.9), sharex=True,
                         gridspec_kw={"height_ratios": heights, "hspace": 0.50})
for ax, (title, sub, rows) in zip(axes, PANELS):
    ys, labels = [], []
    for i, (label, detail, pts, grp) in enumerate(rows):
        y = float(i); color, marker = STYLE[grp]
        vals = [p[0] for p in pts]; bases = [p[1] for p in pts]; base = float(np.median(bases))
        ax.barh(y, base, height=0.56, color=BAND, edgecolor="none", zorder=1)
        ax.plot([base, base], [y - 0.28, y + 0.28], color=INK2, lw=0.9, zorder=2)
        n = len(vals)
        rng = np.random.default_rng(i + 7)
        offs = [0.0] if n == 1 else (np.linspace(-0.16, 0.16, n) if n <= 3 else rng.uniform(-0.2, 0.2, n))
        for v, b, dy in zip(vals, bases, offs):
            above = v > b
            ax.scatter(v, y + dy, s=(26 if above else 20) if n > 3 else 34, marker=marker, zorder=3,
                       linewidth=0.4 if above else 0.9,
                       facecolor=color if above else "white", edgecolor="#fcfcfb" if above else color)
        if n >= 10:
            lo, hi = boot_ci(vals); med = float(np.median(vals))
            ax.plot([lo, hi], [y, y], color=INK, lw=1.3, zorder=4, solid_capstyle="butt")
            ax.plot([med, med], [y - 0.24, y + 0.24], color=INK, lw=1.8, zorder=4)
        k = sum(v > b for v, b in zip(vals, bases))
        ax.text(1.005, y, f"{k}/{n}", transform=ax.get_yaxis_transform(), va="center", ha="left",
                fontsize=9.0, color=INK if k else INK2)
        ys.append(y); labels.append(f"{label}\n{detail}")
    ax.set_yticks(ys); ax.set_yticklabels(labels, fontsize=9.0, linespacing=1.0, color=INK)
    ax.set_ylim(len(rows) - 0.45, -0.6); ax.set_xlim(0, 1.0)
    ax.grid(axis="x", color=GRID, lw=0.6, zorder=0)
    ax.tick_params(axis="y", length=0, pad=5); ax.tick_params(axis="x", length=3, width=0.6)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold", color=INK, pad=13, x=-0.62)
    ax.text(-0.62, 1.02, sub, transform=ax.transAxes, fontsize=9.0, color=INK2, va="bottom")
    ax.text(1.005, -0.75, "above\nbaseline", transform=ax.get_yaxis_transform(), fontsize=8.0,
            color=INK2, ha="left", va="center", linespacing=0.95)
axes[-1].set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
axes[-1].set_xlabel("Persistent share of differences between members (repeatability, R)", color=INK2, labelpad=5)
legend = [Line2D([], [], marker="o", ls="", color=BLUE, markersize=5.5, label="Real groups"),
          Line2D([], [], marker="s", ls="", color=AQUA, markersize=5, label="Rule-based agents"),
          Line2D([], [], marker="^", ls="", color=ORANGE, markersize=5.5, label="LLM agents"),
          Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=INK2, markersize=5,
                 label="Hollow: not above own baseline"),
          Line2D([], [], color=INK, lw=1.3, label="Median, 95% CI"),
          Patch(facecolor=BAND, edgecolor=INK2, linewidth=0.6, label="Shuffled baseline")]
fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=3, frameon=False,
           fontsize=9.0, handletextpad=0.3, columnspacing=0.9)
fig.subplots_adjust(left=0.39, right=0.91, top=0.89, bottom=0.065)
for ext in ("pdf", "png", "svg"):
    fig.savefig(os.path.join(HERE, f"Figure1_audit_v5.{ext}"), dpi=300, facecolor="white")
print("saved")
