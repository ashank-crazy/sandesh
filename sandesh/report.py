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
        for x, y in zip(xs, ys):
            ax.text(x, y + 1.5, f"{y:.0f}", ha="center", va="bottom", fontsize=7, color=INK2)
    ax.set_xticks(range(len(langs)), [LANG_LABELS[l] for l in langs], color=INK)
    ax.set_ylim(0, 108)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("scam SMS flagged (%)  ↑ better", color=INK2)
    ax.set_title("Do off-the-shelf detectors catch Indian scam SMS?", loc="left", color=INK, fontsize=13)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.12), labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


# Diverging map for signed attributions: blue (works against the hijack) <- gray -> red (carries it).
DIVERGING = ["#184f95", "#86b6ef", "#f0efec", "#f2a3a2", "#b8302f"]


def fig_circuit(m: dict, out: Path):
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

    ck = (m.get("extra") or {}).get("circuit") or {}
    panels = [(n, ck[n]) for n in ("base", "safegrad_sandesh") if (ck.get(n) or {}).get("head_grid")]
    if not panels:
        return
    # Robust colour limit: one extreme head (often a negative one in the last layer) would otherwise wash out
    # every other cell. Values beyond the 99th percentile of |score| saturate; the colorbar arrows say so.
    mags = sorted(abs(v) for _, d in panels for row in d["head_grid"] for v in row)
    vmax = mags[int(0.99 * (len(mags) - 1))] if mags else 1.0
    vmax = vmax or (mags[-1] if mags else 0) or 1.0
    cmap = LinearSegmentedColormap.from_list("div", DIVERGING)
    L, H = len(panels[0][1]["head_grid"]), len(panels[0][1]["head_grid"][0])
    fig, axes = plt.subplots(1, len(panels), figsize=(3.2 + 2.6 * len(panels), 0.16 * L + 2.0), dpi=200,
                             facecolor=SURFACE, squeeze=False)
    for ax, (name, d) in zip(axes[0], panels):
        im = ax.imshow(d["head_grid"], cmap=cmap, norm=TwoSlopeNorm(0, -vmax, vmax), aspect="auto",
                       interpolation="nearest")
        for k, _ in d.get("top_heads", [])[:5]:
            l, h = map(int, k[1:].split("."))
            ax.add_patch(plt.Rectangle((h - 0.5, l - 0.5), 1, 1, fill=False, edgecolor=INK, linewidth=1.2))
        ax.set_title(CONDITION_LABELS.get(name, name), loc="left", color=INK, fontsize=10)
        ax.set_xlabel("attention head", color=INK2, fontsize=9)
        ax.set_xticks(range(0, H, max(1, H // 8)))
        ax.set_yticks(range(0, L, max(1, L // 9)))
        ax.tick_params(colors=INK2, length=0, labelsize=8)
        for sp in ax.spines.values():
            sp.set_visible(False)
    axes[0][0].set_ylabel("layer", color=INK2, fontsize=9)
    cb = fig.colorbar(im, ax=axes[0].tolist(), fraction=0.04, pad=0.03, extend="both")
    cb.set_label("EAP-IG score  (red: carries the scam's push to the attacker's tool)", color=INK2, fontsize=8)
    cb.ax.tick_params(colors=INK2, labelsize=7, length=0)
    cb.outline.set_visible(False)
    fig.suptitle("Where the hijack happens: CircuitKIT attribution per attention head (top 5 boxed)",
                 x=0.02, ha="left", color=INK, fontsize=12)
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def fig_knockout(m: dict, out: Path):
    import matplotlib.pyplot as plt

    sw = (((m.get("extra") or {}).get("circuit") or {}).get("base") or {}).get("sweep") or {}
    if not sw.get("top"):
        return
    ks = sorted(sw["top"], key=int)
    xs = list(range(len(ks) + 1))
    labels = ["0"] + ks
    panels = [("attack_beats_task", "Scam present: attacker's tool ranked first (%)  ↓ better"),
              ("task_beats_attack_no_scam", "No scam: task's tool ranked first (%)  ↑ better")]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), dpi=200, facecolor=SURFACE)
    for ax, (key, title) in zip(axes, panels):
        _style(ax)
        b = (sw["baseline"].get("test") or {}).get(key)
        top = [b] + [(sw["top"][k].get("test") or {}).get(key) for k in ks]
        rnd = [b] + [((sw["random"].get(k) or {}).get("test") or {}).get(key) for k in ks]
        for ys, color, lab in ((top, COLORS[0], "top-k CircuitKIT heads zeroed"),
                               (rnd, "#8c8b85", "k random heads zeroed (control)")):
            ax.plot(xs, [100 * (y or 0) for y in ys], color=color, linewidth=2, marker="o", markersize=5,
                    markeredgecolor=SURFACE, markeredgewidth=1.5, label=lab, zorder=3)
        # End labels: one label when both lines end on the same value, pushed apart when they nearly collide.
        e_top, e_rnd = 100 * (top[-1] or 0), 100 * (rnd[-1] or 0)
        if round(e_top) == round(e_rnd):
            ends = [(e_top, e_top)]
        else:
            gap = max(0.0, 7 - abs(e_top - e_rnd)) / 2
            hi, lo = (e_top, e_rnd) if e_top > e_rnd else (e_rnd, e_top)
            ends = [(hi, hi + gap), (lo, lo - gap)]
        for val, y in ends:
            ax.text(xs[-1], y, f"  {val:.0f}%", va="center", fontsize=8, color=INK)
        if sw.get("chosen_k") is not None and str(sw["chosen_k"]) in ks:
            xk = ks.index(str(sw["chosen_k"])) + 1
            ax.axvline(xk, color=INK2, linewidth=0.8, linestyle=":")
            ax.text(xk - 0.1, 103, f"chosen k={sw['chosen_k']}", ha="right", fontsize=8, color=INK2)
        ax.set_xticks(xs, labels)
        ax.set_ylim(0, 108)
        ax.set_yticks(range(0, 101, 20))
        ax.set_xlabel("attention heads zeroed (k)", color=INK2)
        ax.set_title(title, loc="left", color=INK, fontsize=10)
    handles, labs = axes[0].get_legend_handles_labels()
    fig.suptitle("Knocking out the injection heads (held-out test pairs, base model, no training)",
                 x=0.02, ha="left", color=INK, fontsize=12)
    fig.tight_layout(rect=(0, 0.07, 1, 1), w_pad=3)
    fig.legend(handles, labs, frameon=False, fontsize=8, loc="lower center", bbox_to_anchor=(0.5, 0.0), ncol=2,
               labelcolor=INK)
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
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
    fig_circuit(m, res / "fig_circuit_heads.png")
    fig_knockout(m, res / "fig_knockout.png")
    print(f"figures -> {res}")


if __name__ == "__main__":
    main()
