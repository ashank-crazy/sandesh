"""generate() survives CUDA out-of-memory by halving the batch, and keeps every output in order."""

import pytest
import torch

from sandesh.gen import generate


class _Enc(dict):
    def to(self, device):
        return self


class _Tok:
    bos_token, eos_token_id, pad_token_id = None, 0, 0

    def __call__(self, texts, return_tensors, padding, add_special_tokens):
        n = max(len(t) for t in texts)
        # each prompt's tokens encode its own length, so the "model" can answer per prompt
        ids = torch.tensor([[len(t)] * n for t in texts])
        return _Enc(input_ids=ids, attention_mask=torch.ones_like(ids))

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(str(i) for i in ids)


class _Model:
    device = "cpu"

    def __init__(self, max_batch):
        self.max_batch, self.calls = max_batch, []

    def generate(self, input_ids, attention_mask, max_new_tokens, do_sample, pad_token_id):
        self.calls.append(len(input_ids))
        if len(input_ids) > self.max_batch:
            raise torch.cuda.OutOfMemoryError("fake OOM")
        new = torch.stack([input_ids[:, 0], input_ids[:, 0] + 100, torch.zeros_like(input_ids[:, 0])], 1)
        return torch.cat([input_ids, new], 1)


def test_oom_halves_batch_and_keeps_order():
    prompts = ["x" * n for n in (3, 9, 1, 7, 5, 2, 8, 4, 6, 10)]
    model = _Model(max_batch=3)
    outs, stats = generate(model, _Tok(), prompts, max_new_tokens=4, batch_size=8)
    assert outs == [f"{len(p)} {len(p) + 100}" for p in prompts]  # right answer at the right index
    assert model.calls[:3] == [8, 4, 2]  # 8 and 4 fail, then 2 for the rest
    assert set(model.calls[2:]) == {2}
    assert stats["batch_size"] == 8 and stats["batch_size_after_oom"] == 2
    assert stats["new_tokens"] == 2 * len(prompts)


def test_no_oom_keeps_batch_size():
    prompts = ["x" * n for n in range(1, 8)]
    model = _Model(max_batch=99)
    outs, stats = generate(model, _Tok(), prompts, max_new_tokens=4, batch_size=4)
    assert model.calls == [4, 3]
    assert "batch_size_after_oom" not in stats
    assert outs == [f"{len(p)} {len(p) + 100}" for p in prompts]


def test_oom_at_batch_one_raises():
    with pytest.raises(torch.cuda.OutOfMemoryError):
        generate(_Model(max_batch=0), _Tok(), ["ab", "c"], max_new_tokens=4, batch_size=2)
