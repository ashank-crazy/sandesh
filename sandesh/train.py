"""SafeTune stage: fine-tune the assistant to ignore scam instructions.

Three runs, all LoRA (merged into the saved checkpoint), same data budget:

* ``sft_clean``  - PlainSFTTrainer on inboxes with the scam removed.
  Control: learns the tool format and tasks, never sees an injection.
* ``sft_sandesh`` - PlainSFTTrainer on the real inboxes (70% contain a scam;
  the target does the user's task and warns about the scam). Undefended
  fine-tune.
* ``safegrad_sandesh`` - SafeGradTrainer on the same data, with the base
  model's own multilingual refusals as the alignment signal. Gradient surgery
  keeps the general refusal behaviour from drifting while the task is learned.

    python -m sandesh.train --method plain --data data/curated/train --out ckpt/sft_sandesh
    python -m sandesh.train --method safegrad --data data/curated/train --safety data/curated/safety --out ckpt/safegrad_sandesh
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

DEFAULT_BASE = "CohereLabs/tiny-aya-fire"


class _BaseView:
    """SafeGrad's frozen reference, read through the LoRA model with its adapters switched off.

    SafeTune loads the reference as a second full copy of the base model (+6.7 GB of GPU memory for
    Tiny Aya). LoRA never changes the base weights, so the policy with its adapters disabled computes
    exactly the base model's logits: same KL target, no second copy, and SafeGrad fits in the same
    memory as plain SFT. ``parameters()`` is empty, so the trainer's reference-freezing loop cannot
    reach the adapters. ``--reference-copy`` restores SafeTune's own loading.
    """

    def __init__(self, peft_model):
        self._m = peft_model

    @property
    def device(self):
        return next(self._m.parameters()).device

    def eval(self):
        return self

    def to(self, *args, **kwargs):
        return self

    def parameters(self):
        return iter(())

    def __call__(self, **kwargs):
        import torch

        was_training = self._m.training
        self._m.eval()  # the copy SafeTune would load runs in eval mode too
        try:
            with torch.no_grad(), self._m.disable_adapter():
                return self._m(**kwargs)
        finally:
            self._m.train(was_training)


def _share_reference(trainer) -> None:
    """Make ``trainer`` (a SafeGradTrainer) use the policy's own base weights as the reference."""
    from safetune.runner.harden import _gradient_surgery as gs

    policy = {}
    lora_base = trainer._lora_base

    def _capture():
        policy["model"] = lora_base()
        return policy["model"]

    trainer._lora_base = _capture
    gs._load_pretrained_lm = lambda path, **kwargs: _BaseView(policy["model"])


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", choices=["plain", "safegrad"], required=True)
    ap.add_argument("--base", default=os.environ.get("SANDESH_BASE", DEFAULT_BASE))
    ap.add_argument("--data", required=True, help="CuratorKIT export folder (config sft_messages)")
    ap.add_argument("--safety", help="CuratorKIT export folder of refusal chats (safegrad only)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=None, help="None = sized from the data (cap 2048)")
    ap.add_argument("--rho", type=float, default=1.0, help="SafeGrad surgery mixing weight")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--no-grad-ckpt", action="store_true")
    ap.add_argument("--reference-copy", action="store_true",
                    help="safegrad: load the KL reference as a second model copy (SafeTune default) instead of "
                         "reading the base weights through the LoRA model with adapters off (same logits, less memory)")
    ap.add_argument("--device", default=None, help="cuda / cpu (default: best available)")
    args = ap.parse_args(argv)

    import safetune
    from safetune.runner import harden
    from safetune.runner.utils.model_utils import load_model, load_tok

    safetune.configure(seed=args.seed, lora_r=args.lora_r, max_len=args.max_len, device=args.device)
    tok = load_tok(args.base)
    model = load_model(args.base)
    if not args.no_grad_ckpt:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.enable_input_require_grads()

    common = dict(epochs=args.epochs, batch_size=args.bs, lr=args.lr, logging_steps=10)
    kw = {}
    if args.method == "plain":
        trainer = harden.PlainSFTTrainer(model, tok, **common)
    else:
        if not args.safety:
            ap.error("--safety is required for safegrad")
        trainer = harden.SafeGradTrainer(model, tok, rho=args.rho, reference_model_path=args.base, **common)
        if not args.reference_copy:
            _share_reference(trainer)
        kw = dict(safety_dataset=args.safety, safety_dataset_config="sft_messages")

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    path = trainer.train(args.data, out_dir=str(out), dataset_config="sft_messages", **kw)
    meta = {**vars(args), "checkpoint": path, "train_seconds": round(time.time() - t0, 1),
            "trainer": type(trainer).__name__}
    Path(path, "sandesh_train.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
