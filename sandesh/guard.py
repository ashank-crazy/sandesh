"""Off-the-shelf detectors as a defense baseline: screen every SMS before the assistant sees it.

Two detectors, both open and un-gated, used only as baselines (never trained on):

* ``Qwen/Qwen3Guard-Gen-4B`` prompt moderation (multilingual, 119 languages). Strict
  mode flags ``Unsafe`` *and* ``Controversial``, which is the mode you would deploy
  as a filter; loose mode flags only ``Unsafe``.
* ``protectai/deberta-v3-base-prompt-injection-v2``, a popular prompt-injection
  classifier trained on English.

Writes ``data/guard/flags.jsonl`` (one row per scenario: per-message verdicts and kinds)
and ``data/guard/filter_qwen3guard.jsonl`` (``{id, drop}``) for
``sandesh.evaluate --inbox-filter``. Detection rates by language are computed in
``sandesh.score`` because every scam message is known exactly.

    python -m sandesh.guard
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .world import TEST_SPLITS

QWEN_GUARD = "Qwen/Qwen3Guard-Gen-4B"
PROTECTAI = "protectai/deberta-v3-base-prompt-injection-v2"


def _read(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.open(encoding="utf-8")]


def _write(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def qwen_guard(texts: list[str], model_id: str, batch_size: int) -> list[str | None]:
    from .gen import generate, load_model
    from .safety import _free

    model, tok = load_model(model_id)
    prompts = [tok.apply_chat_template([{"role": "user", "content": t}], tokenize=False) for t in texts]
    outs, _ = generate(model, tok, prompts, max_new_tokens=24, batch_size=batch_size, desc="qwen3guard")
    del model
    _free()
    res = []
    for o in outs:
        m = re.search(r"Safety:\s*(Safe|Unsafe|Controversial)", o or "")
        res.append(m.group(1) if m else None)
    return res


def protectai(texts: list[str], model_id: str, batch_size: int) -> list[str]:
    import torch
    from transformers import pipeline

    dev = 0 if torch.cuda.is_available() else -1
    clf = pipeline("text-classification", model=model_id, device=dev, truncation=True, max_length=512)
    return [r["label"] for r in clf(texts, batch_size=batch_size)]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--qwen", default=QWEN_GUARD)
    ap.add_argument("--protectai", default=PROTECTAI)
    ap.add_argument("--bs", type=int, default=32)
    ap.add_argument("--limit", type=int, default=None, help="first N scenarios per split (debug)")
    args = ap.parse_args(argv)

    data = Path(args.data)
    scns = [s for split in TEST_SPLITS for s in _read(data / "scenarios" / f"{split}.jsonl")[: args.limit]]
    texts = sorted({m["text"] for s in scns for m in s["inbox"]})
    print(f"{len(scns)} scenarios, {len(texts)} distinct SMS")
    q = dict(zip(texts, qwen_guard(texts, args.qwen, args.bs)))
    p = dict(zip(texts, protectai(texts, args.protectai, args.bs)))

    rows, drops = [], []
    for s in scns:
        qv = [q[m["text"]] for m in s["inbox"]]
        rows.append({"id": s["id"], "split": s["split"], "lang": s["lang"],
                     "kinds": [m["kind"] for m in s["inbox"]],
                     "qwen": qv, "protectai": [p[m["text"]] for m in s["inbox"]]})
        drops.append({"id": s["id"], "drop": [i for i, v in enumerate(qv) if v in ("Unsafe", "Controversial")]})
    _write(data / "guard" / "flags.jsonl", rows)
    _write(data / "guard" / "filter_qwen3guard.jsonl", drops)
    n_drop = sum(len(d["drop"]) for d in drops)
    print(f"flags -> {data / 'guard'}; Qwen3Guard (strict) would drop {n_drop} of "
          f"{sum(len(s['inbox']) for s in scns)} messages")


if __name__ == "__main__":
    main()
