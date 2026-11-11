"""Run one condition (model + system prompt) over every test split and the harmful-prompt set.

Writes ``runs/<name>/<split>.jsonl`` (id, raw output), ``harmful.jsonl`` and
``perf.json``. Scoring is separate (``sandesh.score``) so transcripts are kept
verbatim and can be re-scored or published.

    python -m sandesh.evaluate --model CohereLabs/tiny-aya-fire --name base
    python -m sandesh.evaluate --model CohereLabs/tiny-aya-fire --name base_defensive --prompt defensive
    python -m sandesh.evaluate --model ckpt/safegrad_sandesh --name safegrad_sandesh
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .tools import apply_chat_template, build_messages
from .world import TEST_SPLITS


def _read(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.open(encoding="utf-8")]


def _write(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--prompt", choices=["base", "defensive"], default="base")
    ap.add_argument("--data", default="data")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--splits", nargs="*", default=TEST_SPLITS)
    ap.add_argument("--no-harmful", action="store_true")
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--limit", type=int, default=None, help="first N scenarios per split (debug)")
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--force", action="store_true", help="redo splits that already have outputs")
    args = ap.parse_args(argv)

    from .gen import generate, load_model

    data, out = Path(args.data), Path(args.runs) / args.name
    out.mkdir(parents=True, exist_ok=True)
    model, tok = load_model(args.model)
    perf = json.loads((out / "perf.json").read_text()) if (out / "perf.json").exists() else {}

    for split in args.splits:
        dst = out / f"{split}.jsonl"
        if dst.exists() and not args.force:
            print(f"skip {split} (exists)")
            continue
        scns = _read(data / "scenarios" / f"{split}.jsonl")[: args.limit]
        prompts = [apply_chat_template(tok, build_messages(s, prompt=args.prompt)) for s in scns]
        outs, stats = generate(model, tok, prompts, args.max_new_tokens, args.bs, desc=f"{args.name}:{split}")
        _write(dst, [{"id": s["id"], "output": o} for s, o in zip(scns, outs)])
        perf[split] = stats
        print(f"{split}: {stats}")

    harm_src = data / "safety" / "harmful_eval.jsonl"
    dst = out / "harmful.jsonl"
    if not args.no_harmful and harm_src.exists() and (args.force or not dst.exists()):
        rows = _read(harm_src)[: args.limit]
        prompts = [apply_chat_template(tok, [{"role": "user", "content": r["prompt"]}]) for r in rows]
        outs, stats = generate(model, tok, prompts, 200, args.bs, desc=f"{args.name}:harmful")
        _write(dst, [{"id": r["id"], "output": o} for r, o in zip(rows, outs)])
        perf["harmful"] = stats

    meta = {"name": args.name, "model": args.model, "prompt": args.prompt,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"), "limit": args.limit}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    (out / "perf.json").write_text(json.dumps(perf, indent=2))


if __name__ == "__main__":
    main()
