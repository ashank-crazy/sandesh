"""Batched greedy generation with plain transformers (works on CUDA, MPS, CPU)."""

from __future__ import annotations

import os
import time
from typing import Optional

import torch


def pick_device(device: Optional[str] = None) -> str:
    if device:
        return device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available() and os.environ.get("SANDESH_ALLOW_MPS") == "1":
        return "mps"
    return "cpu"


def load_model(path: str, device: Optional[str] = None):
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = pick_device(device)
    tok = AutoTokenizer.from_pretrained(path)
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    model = AutoModelForCausalLM.from_pretrained(path, dtype=dtype).to(device).eval()
    return model, tok


@torch.no_grad()
def generate(model, tok, prompts: list[str], max_new_tokens: int = 256, batch_size: int = 16,
             desc: str = "gen") -> tuple[list[str], dict]:
    """Greedy-decode every prompt (already chat-templated). Returns outputs and throughput."""
    from tqdm.auto import tqdm

    if not prompts:
        return [], {"n": 0}
    order = sorted(range(len(prompts)), key=lambda i: -len(prompts[i]))
    add_special = not (tok.bos_token and prompts[0].startswith(tok.bos_token))
    outs: list[Optional[str]] = [None] * len(prompts)
    new_tokens, prompt_tokens, t0 = 0, 0, time.time()
    stop_ids = [i for i in {tok.eos_token_id, tok.pad_token_id} if i is not None]
    for b in tqdm(range(0, len(order), batch_size), desc=desc):
        idx = order[b:b + batch_size]
        enc = tok([prompts[i] for i in idx], return_tensors="pt", padding=True,
                  add_special_tokens=add_special).to(model.device)
        prompt_tokens += int(enc["attention_mask"].sum())
        gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                             pad_token_id=tok.pad_token_id)
        new = gen[:, enc["input_ids"].shape[1]:]
        for j, i in enumerate(idx):
            ids = new[j].tolist()
            n = len(ids)
            for k, t in enumerate(ids):
                if t in stop_ids:
                    n = k
                    break
            new_tokens += n
            outs[i] = tok.decode(ids[:n], skip_special_tokens=True).strip()
    secs = time.time() - t0
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else str(model.device)
    return outs, {"n": len(prompts), "seconds": round(secs, 2), "new_tokens": new_tokens,
                  "prompt_tokens": prompt_tokens,
                  "tok_per_s": round(new_tokens / max(secs, 1e-9), 1),
                  "prompts_per_s": round(len(prompts) / max(secs, 1e-9), 3),
                  "batch_size": batch_size, "device": gpu}
