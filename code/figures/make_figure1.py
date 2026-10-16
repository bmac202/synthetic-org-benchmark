"""Figure 1 for the OS Stage 1 proposal: each group's persistent share of differences
against its own shuffled baseline, on one scale.

Values are those in the proposal's results table (rev 45) and, for assigned roles,
the per-run specimens in code/diffenv_results/{final,gaps_2026-10-16}/specimens.
The grey bar runs from 0 to the shuffled baseline (95th percentile of the
label-permutation null); for rows with several runs or measures it runs to the
highest of their baselines.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, BAND = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#dcdbd5"

# (label, detail, values, baseline, group)
REAL, AI, DESIGN = "real", "ai", "design"
ROWS = [
    ("section", "Real groups"),
    ("Clonal ants, no queen", "time near nestmates", [0.68], 0.13, REAL),
    ("Ants with a queen (first look)", "interactions", [0.56], 0.04, REAL),
    ("Online game players", "carry vs support role", [0.51], 0.15, REAL),
    ("Honey bees (first look)", "food exchanges", [0.43], 0.18, REAL),
    ("Office workers, two sites", "face-to-face contacts", [0.34, 0.28], 0.16, REAL),
    ("section", "AI agents, nothing assigned"),
    ("Self-written memory, out of contact", "moves; memory length", [0.51, 0.82], 0.11, AI),
    ("Same agents, all hear all", "moves; memory length", [0.11, 0.11], 0.12, AI),
    ("Identical agents, Claude Haiku 4.5", "messages; 3 runs", [0.20, 0.12, 0.10], 0.19, AI),
    ("Identical agents, gpt-4.1-mini", "messages; 3 runs", [0.15, 0.08, 0.15], 0.19, AI),
    ("section", "Differences assigned by design"),
    ("Lab economies, built-in advantage", "output in one good", [0.84], 0.03, DESIGN),
    ("AI agents told a specialty, Haiku", "task type; 2 runs", [0.61, 0.63], 0.19, DESIGN),
    ("AI agents told a specialty, gpt", "task type; 2 runs", [0.76, 0.60], 0.22, DESIGN),
]
STYLE = {REAL: (BLUE, "o"), AI: (ORANGE, "^"), DESIGN: (AQUA, "s")}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": MUTED,
    "axes.linewidth": 0.6, "xtick.color": INK2, "ytick.color": INK2,
    "pdf.fonttype": 42, "svg.fonttype": "none",
})

fig, ax = plt.subplots(figsize=(6.5, 5.6))
y = 0.0
ys, labels = [], []
for row in ROWS:
    if row[0] == "section":
        y += 0.35 if ys else 0
        ax.text(-0.012, y, row[1], transform=ax.get_yaxis_transform(), ha="right",
                va="center", fontsize=9, fontweight="bold", color=INK)
        y += 0.9
        continue
    label, detail, vals, base, grp = row
    color, marker = STYLE[grp]
    ax.barh(y, base, height=0.5, color=BAND, edgecolor="none", zorder=1)
    ax.plot([base, base], [y - 0.25, y + 0.25], color=INK2, lw=1.0, zorder=2)
    n = len(vals)
    offsets = [0.0] if n == 1 else [(-0.13 + 0.26 * i / (n - 1)) for i in range(n)]
    for v, dy in zip(vals, offsets):
        ax.scatter(v, y + dy, s=46, marker=marker, color=color, edgecolor="#fcfcfb",
                   linewidth=1.0, zorder=3)
    ys.append(y)
    labels.append(f"{label}\n{detail}")
    y += 1.0

ax.set_yticks(ys)
ax.set_yticklabels(labels, fontsize=8, linespacing=1.15)
for t in ax.get_yticklabels():
    t.set_color(INK)
ax.set_ylim(y - 0.4, -0.7)
ax.set_xlim(0, 0.9)
ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8])
ax.set_xlabel("Persistent share of differences between members (repeatability, R)",
              color=INK2, labelpad=6)
ax.grid(axis="x", color=GRID, lw=0.6, zorder=0)
ax.tick_params(axis="y", length=0, pad=6)
ax.tick_params(axis="x", length=3, width=0.6)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)

legend = [
    Line2D([], [], marker="o", ls="", color=BLUE, markersize=6.5, label="Real groups"),
    Line2D([], [], marker="^", ls="", color=ORANGE, markersize=6.5, label="AI agents, nothing assigned"),
    Line2D([], [], marker="s", ls="", color=AQUA, markersize=6, label="Assigned by design"),
    Patch(facecolor=BAND, edgecolor=INK2, linewidth=0.6,
          label="Shuffled baseline (95th percentile)"),
]
ax.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.36, 1.0), ncol=2,
          frameon=False, fontsize=8, handletextpad=0.4, columnspacing=1.4)

fig.tight_layout()
for ext in ("pdf", "png", "svg"):
    fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"Figure1_benchmark.{ext}"), dpi=300, facecolor="white")
print("saved")
