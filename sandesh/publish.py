"""Push everything the submission needs to Hugging Face (public, un-gated).

* dataset ``<user>/sandesh-bench``: the benchmark (all splits), the curated
  training sets (CuratorKIT exports with provenance), safety prompt splits,
  every model transcript (runs/), and the scored metrics (results/).
* models ``<user>/tiny-aya-fire-sandesh-<variant>``: merged checkpoints.
* two collections ("Sandesh - models", "Sandesh - datasets") for the form.

    python -m sandesh.publish --user <hf-username> [--models safegrad_sandesh sft_sandesh sft_clean]

Tiny Aya is released under CC-BY-NC-4.0; fine-tunes inherit it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DATASET_CARD = """---
license: cc-by-nc-4.0
language: [en, hi, bn, ta, mr]
tags: [prompt-injection, ai-safety, red-teaming, multilingual, code-mixed, agents, india]
pretty_name: SandeshBench
size_categories: [1K<n<10K]
configs:
- config_name: benchmark
  data_files:
  - {{split: train, path: data/scenarios/train.jsonl}}
  - {{split: dev, path: data/scenarios/dev.jsonl}}
  - {{split: test_iid, path: data/scenarios/test_iid.jsonl}}
  - {{split: test_ood_lang, path: data/scenarios/test_ood_lang.jsonl}}
  - {{split: test_ood_style, path: data/scenarios/test_ood_style.jsonl}}
  - {{split: test_ood_both, path: data/scenarios/test_ood_both.jsonl}}
---

# SandeshBench: scam-SMS prompt injection against an on-device assistant

An on-device assistant reads the user's SMS inbox and can `send_sms`, `call`,
`make_upi_payment`, `open_link`, `set_reminder` or `reply_user`. One message in
the inbox is a scam that tries to make the assistant forward an OTP, pay a UPI
ID, open a phishing link or call a number. Every scenario carries an exact,
LLM-free check: the attacker's identifiers (to detect a hijack) and the user's
real task (to detect usefulness).

* Languages: English, Hindi, Hinglish (train); Bengali, Tamil, Marathi (held out).
* Attack styles: direct, fake system message, authority (bank/RBI/police),
  owner impersonation, script switch (train); honorific register and fake
  tool-call JSON (held out).
* Also here: CuratorKIT-curated training sets (`data/curated/*`, with
  manifests, checksums and `lexsi_provenance.json`), every model transcript
  (`runs/*`), and scored results (`results/`).

Code: {repo}

{results}
"""

MODEL_CARD = """---
license: cc-by-nc-4.0
base_model: {base}
language: [en, hi, bn, ta, mr]
tags: [safety, prompt-injection, on-device, agents, safetune, tiny-aya]
datasets: [{dataset}]
---

# {name}

`{base}` fine-tuned with LoRA (merged) to act as an SMS-inbox assistant that
**does the user's task and ignores (and flags) scam instructions inside messages**.
Method: SafeTune `{trainer}`. Data: SandeshBench train split, curated with CuratorKIT.

Prompt format: see `sandesh/tools.py` in {repo} (system prompt with the tool list,
user request, `read_inbox` call, inbox as a tool result; the model answers with
one JSON tool call).

{results}
"""


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", required=True)
    ap.add_argument("--repo-url", default="https://github.com/ashank-crazy/sandesh")
    ap.add_argument("--models", nargs="*", default=["safegrad_sandesh", "sft_sandesh", "sft_clean"])
    ap.add_argument("--base", default="CohereLabs/tiny-aya-fire")
    ap.add_argument("--skip-models", action="store_true")
    args = ap.parse_args(argv)

    from huggingface_hub import HfApi

    api = HfApi()
    results_md = Path("results/summary.md").read_text() if Path("results/summary.md").exists() else ""

    ds_id = f"{args.user}/sandesh-bench"
    api.create_repo(ds_id, repo_type="dataset", private=False, exist_ok=True)
    api.upload_file(path_or_fileobj=DATASET_CARD.format(repo=args.repo_url, results=results_md).encode(),
                    path_in_repo="README.md", repo_id=ds_id, repo_type="dataset")
    for folder in ["data/scenarios", "data/curated", "data/safety", "runs", "results"]:
        if Path(folder).exists():
            api.upload_folder(folder_path=folder, path_in_repo=folder, repo_id=ds_id, repo_type="dataset",
                              ignore_patterns=["*.lock", "__pycache__/*"])
            print(f"uploaded {folder} -> {ds_id}")

    model_ids = []
    if not args.skip_models:
        for variant in args.models:
            ck = Path("ckpt") / variant
            if not ck.exists():
                print(f"skip {variant}: {ck} missing")
                continue
            mid = f"{args.user}/tiny-aya-fire-sandesh-{variant.replace('_sandesh', '').replace('_', '-')}"
            meta = json.loads((ck / "sandesh_train.json").read_text()) if (ck / "sandesh_train.json").exists() else {}
            api.create_repo(mid, private=False, exist_ok=True)
            (ck / "README.md").write_text(MODEL_CARD.format(base=args.base, dataset=ds_id, name=mid,
                                                            trainer=meta.get("trainer", "?"), repo=args.repo_url,
                                                            results=results_md))
            api.upload_folder(folder_path=str(ck), repo_id=mid, ignore_patterns=["checkpoint-*", "runs/*"])
            model_ids.append(mid)
            print(f"uploaded {ck} -> {mid}")

    space_id = None
    explorer = Path("results/explorer.html")
    if explorer.exists():
        space_id = f"{args.user}/sandesh-explorer"
        api.create_repo(space_id, repo_type="space", space_sdk="static", private=False, exist_ok=True)
        card = ("---\ntitle: Sandesh Explorer\nemoji: 📩\ncolorFrom: red\ncolorTo: blue\nsdk: static\n"
                "pinned: false\nlicense: cc-by-nc-4.0\nshort_description: Scam SMS vs on-device Tiny Aya, real transcripts\n---\n")
        api.upload_file(path_or_fileobj=card.encode(), path_in_repo="README.md", repo_id=space_id, repo_type="space")
        api.upload_file(path_or_fileobj=str(explorer), path_in_repo="index.html", repo_id=space_id, repo_type="space")
        print(f"space: https://huggingface.co/spaces/{space_id}")

    for title, items, kind in [("Sandesh - models", model_ids, "model"), ("Sandesh - datasets", [ds_id], "dataset")]:
        if not items:
            continue
        col = api.create_collection(title=title, namespace=args.user, private=False, exists_ok=True,
                                    description="Lexsi AI Safety Hackathon, Track 2: scam-SMS prompt injection on Tiny Aya")
        for it in items:
            try:
                api.add_collection_item(col.slug, item_id=it, item_type=kind, exists_ok=True)
            except Exception as e:  # noqa: BLE001
                print(f"collection add {it}: {e}")
        print(f"collection: https://huggingface.co/collections/{col.slug}")


if __name__ == "__main__":
    main()
