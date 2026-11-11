"""Figures for the write-up, from results/metrics.json.

    python -m sandesh.report --results results
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .score import CONDITION_LABELS, CONDITION_ORDER, SPLIT_LABELS
from .world import TEST_SPLITS

# Categorical slots 1-5, fixed order (validated: CVD + normal-vision separation pass on light).
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, INK2, GRID, SURFACE = "#1f1f1e", "#5c5b55", "#e4e3de", "#ffffff"
LANG_ORDER = ["en", "hi", "hinglish", "bn", "ta", "mr"]
LANG_LABELS = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish",
               "bn": "Bengali*", "ta": "Tamil*", "mr": "Marathi*"}


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK2, length=0, labelsize=10)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _color(c: str, i: int) -> str:
    """Colour follows the condition, never its position in this particular chart."""
    return COLORS[CONDITION_ORDER.index(c) % len(COLORS)] if c in CONDITION_ORDER else COLORS[i % len(COLORS)]


def _pct(x):
    return None if x is None else 100 * x


def fig_asr_by_split(m: dict, conds: list[str], out: Path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=200, facecolor=SURFACE)
    _style(ax)
    n, w = len(conds), 0.8 / len(conds)
    for i, c in enumerate(conds):
        sp = m["conditions"][c]["splits"]
        ys = [_pct(sp.get(s, {}).get("asr", {}).get("rate")) or 0 for s in TEST_SPLITS]
        xs = [j + (i - (n - 1) / 2) * w for j in range(len(TEST_SPLITS))]
        ax.bar(xs, ys, w * 0.92, color=_color(c, i), edgecolor=SURFACE, linewidth=1.5,
               label=CONDITION_LABELS.get(c, c))
        if c in ("base", "safegrad_sandesh"):  # selective direct labels: before and after
            for x, y in zip(xs, ys):
                ax.text(x, y + 1.2, f"{y:.0f}%", ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_xticks(range(len(TEST_SPLITS)), [SPLIT_LABELS[s] for s in TEST_SPLITS], color=INK)
    ax.set_ylabel("Attack success rate (%)  ↓ better", color=INK2)
    ax.set_ylim(0, 100)
    ax.set_title("How often a scam SMS hijacks the on-device assistant", loc="left", color=INK, fontsize=13)
    ax.legend(frameon=False, fontsize=9, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def fig_lang_dumbbell(m: dict, out: Path, before="base", after="safegrad_sandesh"):
    import matplotlib.pyplot as plt

    if before not in m["conditions"] or after not in m["conditions"]:
        return
    b = m["conditions"][before]["all"]["asr_by_lang"]
    a = m["conditions"][after]["all"]["asr_by_lang"]
    langs = [l for l in LANG_ORDER if l in b and l in a]
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=200, facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    for y, l in enumerate(reversed(langs)):
        xb, xa = _pct(b[l]["rate"]), _pct(a[l]["rate"])
        ax.plot([xa, xb], [y, y], color=GRID, linewidth=3, solid_capstyle="round", zorder=1)
        ax.scatter([xb], [y], s=80, color=_color(before, 0), edgecolor=SURFACE, linewidth=2, zorder=2,
                   label=CONDITION_LABELS[before] if y == 0 else None)
        ax.scatter([xa], [y], s=80, color=_color(after, 4), edgecolor=SURFACE, linewidth=2, zorder=3,
                   label=CONDITION_LABELS[after] if y == 0 else None)
        ax.text(xb + 2, y, f"{xb:.0f}%", va="center", fontsize=8, color=INK2)
        ax.text(max(xa - 2, 0), y, f"{xa:.0f}%", va="center", ha="right", fontsize=8, color=INK)
    ax.set_yticks(range(len(langs)), [LANG_LABELS[l] for l in reversed(langs)], color=INK)
    ax.set_xlim(-8, 100)
    ax.set_xlabel("Attack success rate (%)  ·  * = language never seen in training", color=INK2)
    ax.set_title("Scam success by language, before → after", loc="left", color=INK, fontsize=13)
    ax.legend(frameon=False, fontsize=9, loc="lower right", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def fig_tradeoff(m: dict, conds: list[str], out: Path):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 5.4), dpi=200, facecolor=SURFACE)
    _style(ax)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    labelled: list[tuple[float, float]] = []
    for i, c in enumerate(conds):
        al = m["conditions"][c]["all"]
        x, y = _pct(al["asr"]["rate"]), _pct(al["success_clean"]["rate"])
        if x is None or y is None:
            continue
        ax.scatter([x], [y], s=110, color=_color(c, i), edgecolor=SURFACE, linewidth=2, zorder=3,
                   label=CONDITION_LABELS.get(c, c))
        # selective direct labels (before / after only), skipped where they would collide
        if c in ("base", "safegrad_sandesh") and all(abs(x - a) > 12 or abs(y - b) > 6 for a, b in labelled):
            ax.annotate(CONDITION_LABELS.get(c, c), (x, y), xytext=(8, 6), textcoords="offset points",
                        fontsize=8, color=INK)
            labelled.append((x, y))
    ax.set_xlim(-3, 100)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Attack success rate, all test splits (%)  ← better", color=INK2)
    ax.set_ylabel("Task success on clean inboxes (%)  ↑ better", color=INK2)
    ax.set_title("Safety vs usefulness (best = top left)", loc="left", color=INK, fontsize=13)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.14), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="results")
    args = ap.parse_args(argv)
    import matplotlib

    matplotlib.use("Agg")
    res = Path(args.results)
    m = json.loads((res / "metrics.json").read_text())
    conds = [c for c in CONDITION_ORDER if c in m["conditions"]] + \
            [c for c in m["conditions"] if c not in CONDITION_ORDER]
    fig_asr_by_split(m, conds, res / "fig_asr_by_split.png")
    fig_lang_dumbbell(m, res / "fig_asr_by_language.png")
    fig_tradeoff(m, conds, res / "fig_tradeoff.png")
    print(f"figures -> {res}")


if __name__ == "__main__":
    main()
