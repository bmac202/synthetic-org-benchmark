"""Figure 1 (v2, 16 Oct 2026): the emergence audit in three demonstrations.

A  A false positive caught: on gpt-4.1-mini, who receives messages looks like a stable hub
   with fixed names and falls to the baseline once names are randomized (6 runs each;
   diffenv_results/alias_rerun/STATUS.md, column "received").
B  Coordination without specialization: identical agents (names randomized) do not keep to
   a task type; agents told a specialty do (favoured-type R; specimens in
   diffenv_results/{alias_rerun,gaps_2026-10-16,final}).
C  Real groups clear their own baselines (diffenv_results/substrates_*, external_2026-10-06).

Grey bar: 0 to the shuffled baseline (95th percentile of the label-permutation null; the
highest of a row's runs). Markers: one per run or site.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, BAND = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#dcdbd5"
REAL, AI, DESIGN = "real", "ai", "design"
STYLE = {REAL: (BLUE, "o"), AI: (ORANGE, "^"), DESIGN: (AQUA, "s")}

PANELS = [
    ("A  A hub that was a name tag",
     "gpt-4.1-mini, identical agents: persistence in who receives messages (6 runs)",
     [("Fixed names", "agent “A1” is the top receiver in 6 of 6 runs",
       [0.38, 0.44, 0.35, 0.43, 0.65, 0.34], 0.19, AI),
      ("Names randomized", "reruns, colleagues shown under shuffled labels",
       [0.22, 0.07, 0.07, 0.12, 0.04, 0.18], 0.20, AI)]),
    ("B  Coordination without specialization",
     "persistence in which type of task an agent takes",
     [("Identical agents, Haiku 4.5", "names randomized; 3 runs", [0.10, 0.13, 0.12], 0.19, AI),
      ("Identical agents, gpt-4.1-mini", "names randomized; 3 runs", [0.15, 0.12, 0.05], 0.19, AI),
      ("Told a specialty, Haiku 4.5", "2 runs", [0.61, 0.63], 0.19, DESIGN),
      ("Told a specialty, gpt-4.1-mini", "2 runs", [0.76, 0.60], 0.22, DESIGN)]),
    ("C  Real groups clear their own baselines",
     "persistence in each group's recorded behavior",
     [("Clonal ants, no queen", "time near nestmates", [0.68], 0.13, REAL),
      ("Ants with a queen", "interactions (first look)", [0.56], 0.04, REAL),
      ("Online game players", "carry vs support role", [0.51], 0.15, REAL),
      ("Honey bees", "food exchanges (first look)", [0.43], 0.18, REAL),
      ("Office workers, two sites", "face-to-face contacts", [0.34, 0.28], 0.16, REAL)]),
]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": MUTED,
    "axes.linewidth": 0.6, "xtick.color": INK2, "ytick.color": INK2,
    "pdf.fonttype": 42, "svg.fonttype": "none",
})

heights = [len(p[2]) + 0.9 for p in PANELS]
fig, axes = plt.subplots(len(PANELS), 1, figsize=(6.5, 6.4), sharex=True,
                         gridspec_kw={"height_ratios": heights, "hspace": 0.55})
for ax, (title, sub, rows) in zip(axes, PANELS):
    ys, labels = [], []
    for i, (label, detail, vals, base, grp) in enumerate(rows):
        y = float(i)
        color, marker = STYLE[grp]
        ax.barh(y, base, height=0.5, color=BAND, edgecolor="none", zorder=1)
        ax.plot([base, base], [y - 0.25, y + 0.25], color=INK2, lw=1.0, zorder=2)
        n = len(vals)
        offs = [0.0] if n == 1 else [(-0.16 + 0.32 * k / (n - 1)) for k in range(n)]
        for v, dy in zip(vals, offs):
            ax.scatter(v, y + dy, s=40, marker=marker, color=color, edgecolor="#fcfcfb",
                       linewidth=0.9, zorder=3)
        ys.append(y)
        labels.append(f"{label}\n{detail}")
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=7.6, linespacing=1.1, color=INK)
    ax.set_ylim(len(rows) - 0.45, -0.6)
    ax.set_xlim(0, 0.9)
    ax.grid(axis="x", color=GRID, lw=0.6, zorder=0)
    ax.tick_params(axis="y", length=0, pad=5)
    ax.tick_params(axis="x", length=3, width=0.6)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_title(title, loc="left", fontsize=9, fontweight="bold", color=INK, pad=14, x=-0.62)
    ax.text(-0.62, 1.02, sub, transform=ax.transAxes, fontsize=7.6, color=INK2, va="bottom")
axes[-1].set_xticks([0, 0.2, 0.4, 0.6, 0.8])
axes[-1].set_xlabel("Persistent share of differences between members (repeatability, R)",
                    color=INK2, labelpad=6)

legend = [
    Line2D([], [], marker="o", ls="", color=BLUE, markersize=6, label="Real groups"),
    Line2D([], [], marker="^", ls="", color=ORANGE, markersize=6, label="AI agents, nothing assigned"),
    Line2D([], [], marker="s", ls="", color=AQUA, markersize=5.5, label="AI agents, specialty assigned"),
    Patch(facecolor=BAND, edgecolor=INK2, linewidth=0.6, label="Shuffled baseline (95th pct.)"),
]
fig.legend(handles=legend, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=4,
           frameon=False, fontsize=7.4, handletextpad=0.3, columnspacing=1.0)
fig.subplots_adjust(left=0.40, right=0.97, top=0.88, bottom=0.08)

here = os.path.dirname(os.path.abspath(__file__))
for ext in ("pdf", "png", "svg"):
    fig.savefig(os.path.join(here, f"Figure1_audit.{ext}"), dpi=300, facecolor="white")
print("saved")
