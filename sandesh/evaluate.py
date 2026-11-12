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

from .tools import PROMPT_VARIANTS, apply_chat_template, build_messages
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
    ap.add_argument("--prompt", choices=list(PROMPT_VARIANTS), default="base")
    ap.add_argument("--inbox-filter", default=None,
                    help="JSONL of {id, drop:[message indices]}: remove those SMS before the model sees the inbox "
                         "(guard-model filtering baseline)")
    ap.add_argument("--data", default="data")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--splits", nargs="*", default=TEST_SPLITS)
    ap.add_argument("--no-harmful", action="store_true")
    ap.add_argument("--no-benign", action="store_true", help="skip the XSTest over-refusal prompts")
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--limit", type=int, default=None, help="first N scenarios per split (debug)")
    ap.add_argument("--max-new-tokens", type=int, default=256)
    ap.add_argument("--force", action="store_true", help="redo splits that already have outputs")
    args = ap.parse_args(argv)

    from .gen import generate, load_model

    data, out = Path(args.data), Path(args.runs) / args.name
    out.mkdir(parents=True, exist_ok=True)
    pending = [s for s in args.splits if args.force or not (out / f"{s}.jsonl").exists()]
    for kind, flag in (("harmful", args.no_harmful), ("benign", args.no_benign)):
        if not flag and (data / "safety" / f"{kind}_eval.jsonl").exists() and \
                (args.force or not (out / f"{kind}.jsonl").exists()):
            pending.append(kind)
    if not pending:
        print(f"{args.name}: nothing to do (all outputs exist)")
        return
    model, tok = load_model(args.model)
    perf = json.loads((out / "perf.json").read_text()) if (out / "perf.json").exists() else {}
    drops = {r["id"]: set(r["drop"]) for r in _read(Path(args.inbox_filter))} if args.inbox_filter else {}

    for split in args.splits:
        dst = out / f"{split}.jsonl"
        if dst.exists() and not args.force:
            print(f"skip {split} (exists)")
            continue
        scns = _read(data / "scenarios" / f"{split}.jsonl")[: args.limit]
        if drops:
            scns = [dict(s, inbox=[m for i, m in enumerate(s["inbox"]) if i not in drops.get(s["id"], ())])
                    for s in scns]
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

    ben_src = data / "safety" / "benign_eval.jsonl"
    dst = out / "benign.jsonl"
    if not args.no_benign and ben_src.exists() and (args.force or not dst.exists()):
        rows = _read(ben_src)[: args.limit]
        prompts = [apply_chat_template(tok, [{"role": "user", "content": r["prompt"]}]) for r in rows]
        outs, stats = generate(model, tok, prompts, 200, args.bs, desc=f"{args.name}:benign")
        _write(dst, [{"id": r["id"], "output": o} for r, o in zip(rows, outs)])
        perf["benign"] = stats

    meta = {"name": args.name, "model": args.model, "prompt": args.prompt, "inbox_filter": args.inbox_filter,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"), "limit": args.limit}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    (out / "perf.json").write_text(json.dumps(perf, indent=2))


if __name__ == "__main__":
    main()
