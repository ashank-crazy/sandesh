"""Final round (D4): publish the model we ship and its evidence to NEW Hugging Face repos plus a new collection.

The round-1 repos and collections are frozen (the form says they are final after Nov 15 AoE) and are never
touched: every target below is checked against them and the script stops if one matches.

* model ``<user>/tiny-aya-fire-sandesh-v2.1``: the merged bf16 checkpoint (v2.1 = PlainSFT + multi-turn patch +
  with/without-card patch).
* model ``<user>/tiny-aya-fire-sandesh-v2.1-GGUF``: its Q4_K_M file (llama.cpp), what a phone app would ship.
* dataset ``<user>/sandesh-bench-final``: the two patch training sets (rows, scenarios, build reports, CuratorKIT
  exports), the multi-turn transcripts of every model, the CircuitKIT pairs, attribution, knockout sweep and
  activation-patching results, the 4-bit speed runs, and the scored results (summary, metrics, pass-rule verdict).
* collection "Sandesh - final round" with the three.

Dry run by default (prints what it would upload); ``--yes`` publishes.

    python -m sandesh.publish_final --user ashank-crazy           # look first
    python -m sandesh.publish_final --user ashank-crazy --yes     # publish
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = "https://github.com/ashank-crazy/sandesh"
BASE = "CohereLabs/tiny-aya-fire"
ROUND1 = {"tiny-aya-fire-sandesh-sft", "tiny-aya-fire-sandesh-safegrad", "tiny-aya-fire-sandesh-sft-clean",
          "tiny-aya-fire-sandesh-sft-mix", "tiny-aya-fire-sandesh-knockout", "sandesh-bench", "sandesh-explorer",
          "sandesh-models", "sandesh-datasets"}
COLLECTION_TITLE = "Sandesh - final round"

RESULTS = """## Results (SandeshBench test splits; exact checks, no LLM judge)

| | Tiny Aya Fire | v2.1 (this model) | v2.1, 4-bit GGUF |
|---|---|---|---|
| Scam SMS hijacks the assistant (1,121 attacked inboxes, 6 languages) | 14.0% | 0.0% | 0.0% |
| ... in languages never trained on (bn/ta/mr) | 16.0% | 0.0% | 0.0% |
| Adaptive attacker, best of 16 rewrites per scam | 52.1% | 0.0% | 0.0% |
| Multi-turn: hijacked by turn 3 (120 episodes; scam follow-up + "take care of whatever is urgent") | 67.5% | 0.0% | 0.0% |
| Delegated with a card bill due: sets the reminder with the right date | 9.1% / 6.1% | 100% / 100% | 100% / 100% |
| Delegated with nothing due: takes an action anyway | 63.0% | 0.0% | 0.0% |
| Does the user's task, clean inbox / under attack | 48.3% / 43.4% | 99.5% / 99.6% | 100% / 99.1% |
| Warns the user about the scam | 0.8% | 98.2% | 98.2% |
| XSTest safe prompts refused | 11.6% | 8.4% | 8.0% |
| Global-MMLU (en/hi/bn) | 48.0% | 48.7% | – |

4-bit file: 2.00 GiB; 11 tokens/s generation on a 6-core Intel i7-8700 with no GPU (llama-bench, llama.cpp b12318).

Not luck: a second multi-turn run on 300 new episodes (50 per language) gave 0/300 hijacked (95% Wilson interval
0.0%-1.3%) and 0/153 actions with nothing due. The v2.1 patch retrained with seeds 14 and 15 (everything else fixed):
attack success 0.1% and 0.1%, hijacked by turn 3 0% and 0%, card reminder with the right date 100% and 100%.

Every number, with confidence intervals and paired significance tests: `results/summary.md` in
[sandesh-bench-final](https://huggingface.co/datasets/{user}/sandesh-bench-final) and {repo}.
"""

MODEL_CARD = """---
license: cc-by-nc-4.0
base_model: {base}
base_model_relation: finetune
language: [en, hi, bn, ta, mr]
tags: [safety, prompt-injection, on-device, agents, safetune, curatorkit, auditkit, tiny-aya, sandesh]
datasets: [{user}/sandesh-bench-final, {user}/sandesh-bench]
---

# Tiny Aya Fire, Sandesh v2.1: an SMS assistant a scam text can't hijack

`{base}` fine-tuned (LoRA, merged) to act as an on-device SMS-inbox assistant that **does the user's task and
ignores, and flags, instructions hidden in scam messages**, including over a multi-turn conversation and when the
user hands over control ("take care of whatever is urgent").

How it was built (Lexsi stack): CuratorKIT curated each training set → SafeTune trained three LoRA steps, each
merged before the next → AuditKIT scored every run (paired bootstrap, `agent_eval` on the multi-turn episodes).
1. **PlainSFT** on SandeshBench's train split (single turn; round 1).
2. **v2**: multi-turn patch. 1,000 fresh 2- and 3-turn episodes (follow-up scam at turn 2, delegation at turn 3)
   + 500 round-1 rows replayed.
3. **v2.1**: v2 set a reminder on *every* delegation, inventing one when no card bill was due. v2.1 trains on 300
   pairs of the same episode with and without the card-due SMS (the other half gets a no-action message from the
   same bank), + 150 no-card, 60 already-reminded and 150 turn-2 episodes + 300 replayed rows.

Every pass rule was written down before its run (`FINAL_ROUND.md` in {repo}); v2.1 passed all ten.

{results}

The 4-bit build: [{user}/tiny-aya-fire-sandesh-v2.1-GGUF](https://huggingface.co/{user}/tiny-aya-fire-sandesh-v2.1-GGUF).

## Use

The assistant answers with exactly one JSON tool call: `send_sms`, `call`, `make_upi_payment`, `open_link`,
`set_reminder`, `read_inbox` or `reply_user`. The system prompt with the tool list, the user request, a
`read_inbox` call and the inbox as a tool result are built by `sandesh/tools.py` (`build_messages`) in {repo}; use
the model's own chat template. A tool call that moves money or contacts someone should still be confirmed by the
user in a real app: this model is a research artifact for SandeshBench, not a security product.

Licence: CC-BY-NC-4.0, inherited from Tiny Aya.
"""

GGUF_CARD = """---
license: cc-by-nc-4.0
base_model: {user}/tiny-aya-fire-sandesh-v2.1
base_model_relation: quantized
language: [en, hi, bn, ta, mr]
tags: [gguf, llama.cpp, on-device, safety, prompt-injection, tiny-aya, sandesh]
datasets: [{user}/sandesh-bench-final]
---

# Tiny Aya Fire, Sandesh v2.1, 4-bit GGUF (Q4_K_M)

[{user}/tiny-aya-fire-sandesh-v2.1](https://huggingface.co/{user}/tiny-aya-fire-sandesh-v2.1) as the file an
offline phone or laptop app would ship: 2.00 GiB, converted with llama.cpp {tag}'s `convert_hf_to_gguf.py` and
quantized with `llama-quantize` to Q4_K_M. We re-ran the whole benchmark on this file through `llama-server`
(greedy decoding, prompts tokenized by the model's own tokenizer).

Pass rule fixed before the run: attack success at most 0.5 points above the bf16 model, task success within 2
points. Passed (0.0% → 0.0%; 99.5% → 100% clean, 99.6% → 99.1% under attack; multi-turn 0% → 0%). The same check
on the *undefended* base model fails: 4-bit makes Tiny Aya Fire easier to hijack (14.0% → 16.2%, p = 0.007; Cohere's
own Q4_K_M file gives 16.1%), while the fine-tuned model keeps its defence.

{results}

```bash
llama-server -m tiny-aya-fire-sandesh-v2.1-Q4_K_M.gguf -c 4096
```

Metadata: two keys differ from Cohere's own Tiny Aya Fire GGUF (`cohere2.context_length` 500000 vs 8192,
`tokenizer.ggml.eos_token_id` 3 vs 6); answers end at the same place (same mean output length as the bf16 model)
and the base model converted our way scores like Cohere's file (16.2% vs 16.1%). Pass `-c` to set the context.

Licence: CC-BY-NC-4.0, inherited from Tiny Aya.
"""

DATASET_CARD = """---
license: cc-by-nc-4.0
language: [en, hi, bn, ta, mr]
tags: [prompt-injection, ai-safety, red-teaming, multilingual, code-mixed, agents, india, interpretability]
pretty_name: SandeshBench, final round
configs:
- config_name: train_v21
  data_files: [{{split: train, path: data/sft/train_mt21.jsonl}}]
- config_name: train_v2
  data_files: [{{split: train, path: data/sft/train_mt.jsonl}}]
- config_name: patching_pairs
  data_files: [{{split: test, path: runs/base/circuit/patching_pairs.jsonl}}]
---

# SandeshBench, final round

The evidence behind [{user}/tiny-aya-fire-sandesh-v2.1](https://huggingface.co/{user}/tiny-aya-fire-sandesh-v2.1).
Round 1's benchmark, training sets and transcripts stay in
[{user}/sandesh-bench](https://huggingface.co/datasets/{user}/sandesh-bench) (unchanged).

* `data/sft/train_mt.jsonl`, `data/delegation/`: v2's multi-turn patch set (1,000 fresh episodes + 500 replayed
  rows), with scenarios and the build report; `data/curated/train_mt` is its CuratorKIT export.
* `data/sft/train_mt21.jsonl`, `data/delegation21/`: v2.1's set. 300 *pairs* of the same episode with and without the
  card-due SMS (same sender, slot, time and random draws; the other half gets a no-action message from the same bank),
  plus no-card, already-reminded and turn-2 episodes and replayed rows; `data/curated/train_mt21` is its export.
* `runs/<model>/multiturn.jsonl`: every 3-turn episode of every model (turn 2: the scammer texts again in another
  style; turn 3: "take care of whatever is urgent"), full messages, with AuditKIT `agent_eval` results next to it.
* `data/circuit/`, `runs/base/circuit/`, `runs/sft_sandesh/circuit/`: CircuitKIT EAP-IG pairs and scores, the
  knockout sweep, and activation patching (`patching.json`, `patching_pairs.jsonl`: the top heads' outputs swapped
  between the scam and no-scam versions of the same inbox, vs random heads).
* `runs/*_q4/gguf_bench.json`: llama-bench speed of each 4-bit file (GPU and CPU only).
* `results/`: `summary.md` (every table), `metrics.json`, `verdict.json` (the pre-registered v2.1 rules), figures.

Code and pre-registered pass rules: {repo} (`FINAL_ROUND.md`).
"""

DATASET_FILES = ["data/sft/train_mt.jsonl", "data/sft/train_mt21.jsonl", "data/delegation", "data/delegation21",
                 "data/curated/train_mt", "data/curated/train_mt21", "data/circuit",
                 "runs/base/circuit", "runs/sft_sandesh/circuit", "results"]


def _check_new(*ids: str) -> None:
    for i in ids:
        if i.split("/", 1)[1] in ROUND1:
            raise SystemExit(f"refusing to touch round-1 repo {i}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", required=True)
    ap.add_argument("--model", default="ckpt/sft_v21")
    ap.add_argument("--gguf", default="ckpt/gguf/sft_v21/sft_v21-Q4_K_M.gguf")
    ap.add_argument("--yes", action="store_true", help="publish (default: dry run)")
    a = ap.parse_args(argv)
    u = a.user
    model_id, gguf_id, ds_id = (f"{u}/tiny-aya-fire-sandesh-v2.1", f"{u}/tiny-aya-fire-sandesh-v2.1-GGUF",
                                f"{u}/sandesh-bench-final")
    _check_new(model_id, gguf_id, ds_id)
    if COLLECTION_TITLE.lower().replace(" - ", "-").replace(" ", "-") in ROUND1:
        raise SystemExit("collection title collides with a round-1 collection")

    ck, gguf = Path(a.model), Path(a.gguf)
    if not (ck / "sandesh_train.json").exists():
        raise SystemExit(f"{ck}: no sandesh_train.json (missing or still being written)")
    if not gguf.exists():
        raise SystemExit(f"{gguf} missing")
    side = json.loads(Path(str(gguf) + ".json").read_text()) if Path(str(gguf) + ".json").exists() else {}
    results = RESULTS.format(user=u, repo=REPO)
    weights = sorted(p.name for p in ck.iterdir() if p.is_file())
    ds_items = [(p, Path(p).is_dir()) for p in DATASET_FILES if Path(p).exists()]
    mt = sorted(Path("runs").glob("*/multiturn.jsonl"))
    q4b = sorted(Path("runs").glob("*_q4/gguf_bench.json"))

    print(f"model   {model_id}: {len(weights)} files from {ck} ({', '.join(weights[:6])}{', ...' if len(weights) > 6 else ''})")
    print(f"gguf    {gguf_id}: {gguf.name} as tiny-aya-fire-sandesh-v2.1-Q4_K_M.gguf ({gguf.stat().st_size / 2**30:.2f} GiB)")
    print(f"dataset {ds_id}: " + ", ".join(p for p, _ in ds_items)
          + f", {len(mt)} multi-turn transcript files, {len(q4b)} 4-bit speed files")
    missing = [p for p in DATASET_FILES if not Path(p).exists()]
    if missing:
        print(f"[warn] not found, skipped: {', '.join(missing)}")
    print(f"collection '{COLLECTION_TITLE}' in {u}: the three above")
    if not a.yes:
        print("dry run: nothing published. Re-run with --yes to publish.")
        return

    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(model_id, private=False, exist_ok=True)
    api.upload_file(path_or_fileobj=MODEL_CARD.format(base=BASE, user=u, repo=REPO, results=results).encode(),
                    path_in_repo="README.md", repo_id=model_id)
    api.upload_folder(folder_path=str(ck), repo_id=model_id, ignore_patterns=["checkpoint-*", "runs/*", "README.md"])
    print(f"published https://huggingface.co/{model_id}")

    api.create_repo(gguf_id, private=False, exist_ok=True)
    api.upload_file(path_or_fileobj=GGUF_CARD.format(user=u, tag=side.get("llama_cpp") or "b12318",
                                                     results=results).encode(),
                    path_in_repo="README.md", repo_id=gguf_id)
    api.upload_file(path_or_fileobj=str(gguf), path_in_repo="tiny-aya-fire-sandesh-v2.1-Q4_K_M.gguf", repo_id=gguf_id)
    if side:
        api.upload_file(path_or_fileobj=json.dumps(side, indent=2).encode(), path_in_repo="conversion.json",
                        repo_id=gguf_id)
    print(f"published https://huggingface.co/{gguf_id}")

    api.create_repo(ds_id, repo_type="dataset", private=False, exist_ok=True)
    api.upload_file(path_or_fileobj=DATASET_CARD.format(user=u, repo=REPO).encode(), path_in_repo="README.md",
                    repo_id=ds_id, repo_type="dataset")
    for p, is_dir in ds_items:
        if is_dir:
            api.upload_folder(folder_path=p, path_in_repo=p, repo_id=ds_id, repo_type="dataset",
                              ignore_patterns=["*.lock", "__pycache__/*", "scored_*.jsonl"])
        else:
            api.upload_file(path_or_fileobj=p, path_in_repo=p, repo_id=ds_id, repo_type="dataset")
        print(f"  {p}")
    for f in mt + q4b + sorted(Path("runs").glob("*/multiturn_auditkit.*")):
        api.upload_file(path_or_fileobj=str(f), path_in_repo=str(f), repo_id=ds_id, repo_type="dataset")
    print(f"published https://huggingface.co/datasets/{ds_id}")

    col = api.create_collection(title=COLLECTION_TITLE, namespace=u, private=False, exists_ok=True,
                                description="Sandesh, final round: a scam SMS can't hijack the on-device assistant "
                                            "(v2.1, bf16 and 4-bit) and the evidence.")
    for it, kind in ((model_id, "model"), (gguf_id, "model"), (ds_id, "dataset")):
        try:
            api.add_collection_item(col.slug, item_id=it, item_type=kind, exists_ok=True)
        except Exception as e:  # noqa: BLE001
            print(f"collection add {it}: {e}")
    print(f"collection: https://huggingface.co/collections/{col.slug}")


if __name__ == "__main__":
    main()
