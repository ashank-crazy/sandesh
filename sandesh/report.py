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


# Five charted slots, one fixed colour each (colour follows the condition in every figure).
# Slot 2 shows the strongest prompt defense that was run. Everything else is table-only.
SLOTS = [["base"], ["base_spotlight", "base_defensive"], ["base_guard"], ["sft_sandesh"], ["safegrad_sandesh"]]


def chart_conds(available) -> list[str]:
    avail = set(available)
    picked = []
    for slot in SLOTS:
        c = next((c for c in slot if c in avail), None)
        if c:
            picked.append(c)
    return picked


def _color(c: str, i: int = 0) -> str:
    for j, slot in enumerate(SLOTS):
        if c in slot:
            return COLORS[j]
    return COLORS[i % len(COLORS)]


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


def _line_chart(series: dict, xs: list, out: Path, title: str, xlabel: str, ylabel: str, logx: bool = False,
                xticks: list | None = None):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=200, facecolor=SURFACE)
    _style(ax)
    for c, ys in series.items():
        ax.plot(xs[:len(ys)], [100 * y for y in ys], color=_color(c), linewidth=2, marker="o", markersize=5,
                markeredgecolor=SURFACE, markeredgewidth=1.5, label=CONDITION_LABELS.get(c, c), zorder=3)
        ax.text(xs[len(ys) - 1], 100 * ys[-1], f"  {100 * ys[-1]:.0f}%", va="center", fontsize=8, color=INK)
    if logx:
        ax.set_xscale("log", base=2)
    if xticks:
        ax.set_xticks(xticks, [str(x) for x in xticks])
    ax.set_ylim(0, 100)
    ax.set_xlabel(xlabel, color=INK2)
    ax.set_ylabel(ylabel, color=INK2)
    ax.set_title(title, loc="left", color=INK, fontsize=13)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.16), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def fig_bon(m: dict, out: Path):
    bon = (m.get("extra") or {}).get("bon") or {}
    conds = chart_conds(bon)
    if not conds:
        return
    K = max(bon[c]["K"] for c in conds)
    _line_chart({c: bon[c]["curve"] for c in conds}, list(range(1, K + 1)), out,
                "Attack success when the scammer gets k tries", "attempts per scenario (k)",
                "attack success rate (%)  ↓ better", logx=True, xticks=[k for k in (1, 2, 4, 8, 16, 32) if k <= K])


def fig_multiturn(m: dict, out: Path):
    mt = (m.get("extra") or {}).get("multiturn") or {}
    conds = chart_conds(mt)
    if not conds:
        return
    series = {c: [(mt[c]["compromised_by_turn"].get(str(t)) or mt[c]["compromised_by_turn"].get(t) or {}).get("rate") or 0
                  for t in (1, 2, 3)] for c in conds}
    _line_chart(series, [1, 2, 3], out, "Hijacked by turn: the scammer follows up, the user delegates",
                "user turn", "episodes hijacked so far (%)  ↓ better", xticks=[1, 2, 3])


def fig_detectors(m: dict, out: Path):
    import matplotlib.pyplot as plt

    det = (m.get("extra") or {}).get("detectors") or {}
    if not det:
        return
    langs = [l for l in LANG_ORDER if any(l in v["recall_by_lang"] for v in det.values())]
    fig, ax = plt.subplots(figsize=(9, 4.4), dpi=200, facecolor=SURFACE)
    _style(ax)
    n, w = len(det), 0.8 / len(det)
    for i, (name, v) in enumerate(det.items()):
        xs = [j + (i - (n - 1) / 2) * w for j in range(len(langs))]
        ys = [100 * (v["recall_by_lang"].get(l, {}).get("rate") or 0) for l in langs]
        ax.bar(xs, ys, w * 0.92, color=COLORS[i % len(COLORS)], edgecolor=SURFACE, linewidth=1.5, label=name)
    ax.set_xticks(range(len(langs)), [LANG_LABELS[l] for l in langs], color=INK)
    ax.set_ylim(0, 100)
    ax.set_ylabel("scam SMS flagged (%)  ↑ better", color=INK2)
    ax.set_title("Do off-the-shelf detectors catch Indian scam SMS?", loc="left", color=INK, fontsize=13)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.12), labelcolor=INK)
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
    charted = chart_conds(conds)
    fig_asr_by_split(m, charted, res / "fig_asr_by_split.png")
    fig_lang_dumbbell(m, res / "fig_asr_by_language.png")
    fig_tradeoff(m, charted, res / "fig_tradeoff.png")
    fig_bon(m, res / "fig_bon_curve.png")
    fig_multiturn(m, res / "fig_multiturn.png")
    fig_detectors(m, res / "fig_detectors.png")
    print(f"figures -> {res}")


if __name__ == "__main__":
    main()
