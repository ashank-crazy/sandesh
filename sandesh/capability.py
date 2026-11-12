"""Capability retention: did hardening make the model dumber?

The same 200 Global-MMLU questions (Cohere Labs, ``CohereLabs/Global-MMLU``, open) in
English, Hindi and Bengali, so languages are compared on identical content. Scored by
the next-token logits of the four option letters (one forward pass per question, no
sampling, no parsing).

    python -m sandesh.capability --model CohereLabs/tiny-aya-fire --name base
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

LANGS = ["en", "hi", "bn"]
LETTERS = ["A", "B", "C", "D"]


def load_questions(n: int, seed: int) -> list[dict]:
    import pandas as pd
    from huggingface_hub import hf_hub_download

    dfs = {l: pd.read_parquet(hf_hub_download("CohereLabs/Global-MMLU", f"{l}/test-00000-of-00001.parquet",
                                              repo_type="dataset")).set_index("sample_id") for l in LANGS}
    common = sorted(set.intersection(*(set(d.index) for d in dfs.values())))
    ids = random.Random(f"gmmlu:{seed}").sample(common, n)
    out = []
    for l in LANGS:
        d = dfs[l]
        for sid in ids:
            r = d.loc[sid]
            out.append({"id": f"{l}:{sid}", "lang": l, "subject": r["subject_category"], "answer": r["answer"],
                        "prompt": f"{r['question']}\nA. {r['option_a']}\nB. {r['option_b']}\nC. {r['option_c']}\n"
                                  f"D. {r['option_d']}\n\nAnswer with the letter of the correct option only."})
    return out


def run(model_path: str, name: str, runs: Path, n: int, seed: int, bs: int, force: bool) -> None:
    import torch

    from .gen import load_model
    from .tools import apply_chat_template

    dst = runs / name / "capability.jsonl"
    if dst.exists() and not force:
        print(f"skip {dst} (exists)")
        return
    qs = load_questions(n, seed)
    model, tok = load_model(model_path)
    cand = [sorted({tok.encode(v, add_special_tokens=False)[0] for v in (L, " " + L)}) for L in LETTERS]
    prompts = [apply_chat_template(tok, [{"role": "user", "content": q["prompt"]}]) for q in qs]
    add_special = not (tok.bos_token and prompts[0].startswith(tok.bos_token))
    preds = []
    with torch.no_grad():
        for b in range(0, len(prompts), bs):
            enc = tok(prompts[b:b + bs], return_tensors="pt", padding=True,
                      add_special_tokens=add_special).to(model.device)
            logits = model(**enc).logits[:, -1, :].float()
            scores = torch.stack([logits[:, ids].max(dim=1).values for ids in cand], dim=1)
            preds += [LETTERS[i] for i in scores.argmax(dim=1).tolist()]
    rows = [{"id": q["id"], "lang": q["lang"], "subject": q["subject"], "answer": q["answer"], "pred": p,
             "correct": p == q["answer"]} for q, p in zip(qs, preds)]
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    acc = {l: sum(r["correct"] for r in rows if r["lang"] == l) / max(1, sum(r["lang"] == l for r in rows))
           for l in LANGS}
    print(f"capability {name}: " + ", ".join(f"{l} {100 * a:.1f}%" for l, a in acc.items()))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--n", type=int, default=200, help="questions per language")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    run(args.model, args.name, Path(args.runs), args.n, args.seed, args.bs, args.force)


if __name__ == "__main__":
    main()
