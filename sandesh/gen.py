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
    """Greedy-decode every prompt (already chat-templated). Returns outputs and throughput.

    On CUDA out-of-memory the batch size halves for the rest of the call and the batch is retried,
    so a large ``batch_size`` is safe on a GPU that other jobs share. Prompts run longest first,
    so if memory is short it shows on the first batch.
    """
    from tqdm.auto import tqdm

    if not prompts:
        return [], {"n": 0}
    order = sorted(range(len(prompts)), key=lambda i: -len(prompts[i]))
    add_special = not (tok.bos_token and prompts[0].startswith(tok.bos_token))
    outs: list[Optional[str]] = [None] * len(prompts)
    new_tokens, prompt_tokens, t0 = 0, 0, time.time()
    stop_ids = [i for i in {tok.eos_token_id, tok.pad_token_id} if i is not None]
    bs, b = batch_size, 0
    bar = tqdm(total=len(order), desc=desc, unit="prompt")
    while b < len(order):
        idx = order[b:b + bs]
        enc = tok([prompts[i] for i in idx], return_tensors="pt", padding=True,
                  add_special_tokens=add_special).to(model.device)
        oom = False
        try:
            gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                                 pad_token_id=tok.pad_token_id)
        except torch.cuda.OutOfMemoryError:
            if bs == 1:
                raise
            oom = True
        if oom:  # outside the except block, so the failed attempt's tensors are already released
            del enc
            bs = max(1, bs // 2)
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            tqdm.write(f"[{desc}] CUDA out of memory: batch size -> {bs}")
            continue
        prompt_tokens += int(enc["attention_mask"].sum())
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
        b += len(idx)
        bar.update(len(idx))
    bar.close()
    secs = time.time() - t0
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else str(model.device)
    stats = {"n": len(prompts), "seconds": round(secs, 2), "new_tokens": new_tokens,
             "prompt_tokens": prompt_tokens,
             "tok_per_s": round(new_tokens / max(secs, 1e-9), 1),
             "prompts_per_s": round(len(prompts) / max(secs, 1e-9), 3),
             "batch_size": batch_size, "device": gpu}
    if bs != batch_size:
        stats["batch_size_after_oom"] = bs
    return outs, stats
