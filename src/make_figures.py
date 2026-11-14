"""Draw Figures 2 and 3 of the paper from results/stats.json (Figure 1: make_framework_figure.py).

Usage: python src/make_figures.py
"""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = ["Times New Roman", "Liberation Serif", "DejaVu Serif"]
S = json.load(open(os.path.join(ROOT, "results", "stats.json")))
DARK, LIGHT, ORANGE = "#3A5F80", "#95AEC4", "#B5651D"
os.makedirs(os.path.join(ROOT, "figures"), exist_ok=True)

# Figure 2: AST agreement and parsing success per arm
fig, axs = plt.subplots(1, 2, figsize=(6.25, 2.6), dpi=250, sharey=True)
for ax, (key, title) in zip(axs, [("ast", "Reference AST agreement (primary)"), ("parse", "Parsing success")]):
    for i, m in enumerate(["DeepSeek", "Claude"]):
        v = S[m][key]
        for j, (arm, c) in enumerate([("natp", DARK), ("synp", LIGHT)]):
            x = i + (j - 0.5) * 0.36
            ax.bar(x, v[arm], 0.34, color=c,
                   label=("Natural" if j == 0 else "Synthetic") if i == 0 and key == "ast" else None)
            ax.text(x, v[arm] + 0.3, f"{v[arm]:.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["DeepSeek", "Claude"], fontsize=9.5)
    ax.set_title(title, fontsize=9.5)
    ax.set_ylim(80, 101.5); ax.grid(axis="y", color="#ddd", lw=0.6); ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(labelsize=8.5)
axs[0].set_ylabel("% of 300 pairs", fontsize=9)
fig.legend(loc="upper center", ncol=2, frameon=False, fontsize=8.5, bbox_to_anchor=(0.5, 1.0))
fig.tight_layout(rect=(0, 0, 1, 0.88))
fig.savefig(os.path.join(ROOT, "figures", "fig2_primary.png"))

# Figure 3: natural minus synthetic AST agreement by family
NAMES = [("ALL", "All families"), ("BRACKET_MISMATCH", "Bracket mismatch"), ("MISSING_CLOSER", "Missing closer"),
         ("MISSING_COLON", "Missing colon"), ("MISSING_COMMA", "Missing comma"),
         ("PRINT_STATEMENT", "Print statement"), ("QUOTATION", "Quotation")]
fig, ax = plt.subplots(figsize=(6.25, 3.0), dpi=250)
for k, (fam, label) in enumerate(NAMES):
    for j, (m, c) in enumerate([("DeepSeek", DARK), ("Claude", ORANGE)]):
        v = S[m]["ast"] if fam == "ALL" else S[m]["fam"][fam]
        y = k + (j - 0.5) * 0.26
        ax.errorbar(v["diff"], y, xerr=[[v["diff"] - v["ci"][0]], [v["ci"][1] - v["diff"]]],
                    fmt="o", color=c, ms=4, capsize=3, lw=1, label=m if k == 0 else None)
ax.set_yticks(range(len(NAMES)))
ax.set_yticklabels(["%s (%d)" % (l, (S["DeepSeek"]["ast"] if f == "ALL" else S["DeepSeek"]["fam"][f])["n"])
                    for f, l in NAMES], fontsize=8.5)
ax.invert_yaxis(); ax.axvline(0, color="grey", lw=1)
ax.grid(axis="x", color="#ddd", lw=0.6); ax.set_axisbelow(True)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
ax.set_xlabel("Natural minus synthetic AST agreement (percentage points)", fontsize=8.5)
ax.legend(loc="lower right", frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(os.path.join(ROOT, "figures", "fig3_families.png"))
print("figures written to", os.path.join(ROOT, "figures"))
