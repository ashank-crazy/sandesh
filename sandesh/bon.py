"""Best-of-N adaptive attack: does the defense hold when the attacker gets K tries?

``build`` picks N attacked scenarios per language from the test splits and writes K
rewrites of each scam (``sandesh.attacks``: character noise, encoding tricks, urgency,
re-styling, sender spoofing, position). ``run`` answers every rewrite with one condition.
``sandesh.score`` turns the outputs into ASR@k curves (attacker wins a scenario if any of
the first k attempts hijacks the assistant), ASR by augmentation family and by language.

    python -m sandesh.bon build --per-lang 30 --k 16
    python -m sandesh.bon run --model CohereLabs/tiny-aya-fire --name base
    python -m sandesh.bon run --model ckpt/safegrad_sandesh --name safegrad_sandesh
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from . import lang as LG
from .attacks import bon_plan, bon_variant
from .tools import PROMPT_VARIANTS, apply_chat_template, build_messages
from .world import TEST_SPLITS


def _read(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.open(encoding="utf-8")]


def _write(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def select(data: Path, per_lang: int, seed: int) -> list[dict]:
    """``per_lang`` attacked scenarios per language, spread evenly over goals and splits."""
    by = defaultdict(list)
    for split in TEST_SPLITS:
        for s in _read(data / "scenarios" / f"{split}.jsonl"):
            if s["injected"]:
                by[(s["lang"], s["goal"])].append(s)
    rng = random.Random(f"bon-select:{seed}")
    out = []
    for lang in LG.ALL_LANGS:
        pools = [sorted(by[(lang, g)], key=lambda s: s["id"]) for g in LG.GOALS]
        for p in pools:
            rng.shuffle(p)
        picked, i = [], 0
        while len(picked) < per_lang and any(i < len(p) for p in pools):
            picked += [p[i] for p in pools if i < len(p)]
            i += 1
        out += picked[:per_lang]
    return out


def build(data: Path, per_lang: int, k: int, seed: int) -> None:
    rows = []
    for s in select(data, per_lang, seed):
        for j, ops in enumerate(bon_plan(s["id"], k)):
            v = bon_variant(s, ops, seed=f"{seed}:{s['id']}:{j}")
            rows.append({**v, "id": f"{s['id']}~{j:02d}", "base_id": s["id"], "attempt": j, "ops": ops})
    _write(data / "bon" / "scenarios.jsonl", rows)
    print(f"bon: {len(rows) // max(k, 1)} scenarios x {k} attempts = {len(rows)} prompts -> {data / 'bon'}")


def run(model_path: str, name: str, prompt: str, data: Path, runs: Path, bs: int, max_new_tokens: int,
        limit: int | None, force: bool) -> None:
    from .gen import generate, load_model

    out = runs / name
    dst = out / "bon.jsonl"
    if dst.exists() and not force:
        print(f"skip {dst} (exists)")
        return
    rows = _read(data / "bon" / "scenarios.jsonl")[:limit]
    model, tok = load_model(model_path)
    prompts = [apply_chat_template(tok, build_messages(r, prompt=prompt)) for r in rows]
    outs, stats = generate(model, tok, prompts, max_new_tokens, bs, desc=f"{name}:bon")
    _write(dst, [{"id": r["id"], "base_id": r["base_id"], "attempt": r["attempt"], "output": o}
                 for r, o in zip(rows, outs)])
    pf = out / "perf.json"
    perf = json.loads(pf.read_text()) if pf.exists() else {}
    perf["bon"] = stats
    pf.write_text(json.dumps(perf, indent=2))
    print(f"bon {name}: {stats}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "run"])
    ap.add_argument("--data", default="data")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--per-lang", type=int, default=30)
    ap.add_argument("--k", type=int, default=16)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--model")
    ap.add_argument("--name")
    ap.add_argument("--prompt", choices=list(PROMPT_VARIANTS), default="base")
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--max-new-tokens", type=int, default=160)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "build":
        build(Path(args.data), args.per_lang, args.k, args.seed)
    else:
        if not (args.model and args.name):
            ap.error("run needs --model and --name")
        run(args.model, args.name, args.prompt, Path(args.data), Path(args.runs), args.bs, args.max_new_tokens,
            args.limit, args.force)


if __name__ == "__main__":
    main()
