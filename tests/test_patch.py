import json

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from sandesh import circuit as C  # noqa: E402
from sandesh.score_extra import circuit_markdown, circuit_summary  # noqa: E402

L, H = 3, 4


def _model():
    torch.manual_seed(0)
    cfg = transformers.LlamaConfig(vocab_size=50, hidden_size=32, intermediate_size=64, num_hidden_layers=L,
                                   num_attention_heads=H, num_key_value_heads=2, max_position_embeddings=64)
    return transformers.LlamaForCausalLM(cfg).eval()


class _Tok:
    def __call__(self, text, return_tensors=None, add_special_tokens=False):
        return {"input_ids": torch.tensor([[int(t) for t in text.split()]])}


EVERY = [(l, h) for l in range(L) for h in range(H)]


def test_self_patch_is_a_no_op_and_hooks_are_removed():
    m = _model()
    a = {"input_ids": torch.tensor([[1, 2, 3, 4, 5, 6]])}
    b = {"input_ids": torch.tensor([[1, 2, 9, 9, 5, 6]])}
    with torch.no_grad():
        acts_a, la = C.capture_heads(m, a)
        acts_b, _ = C.capture_heads(m, b)
        assert set(acts_a) == set(range(L)) and acts_a[0].shape == (1, 6, 32)
        with C.patched(m, EVERY, acts_a):
            assert torch.allclose(C._forward_last(m, a), la, atol=1e-6)
        with C.patched(m, [(2, 1), (1, 3)], acts_b):
            assert not torch.allclose(C._forward_last(m, a), la)
        assert torch.allclose(C._forward_last(m, a), la, atol=1e-6)
        with pytest.raises(ValueError):
            with C.patched(m, [(0, 0)], C.capture_heads(m, {"input_ids": torch.tensor([[1, 2, 3]])})[0]):
                C._forward_last(m, a)


def test_patch_command_writes_results_and_table(tmp_path, monkeypatch):
    data, runs = tmp_path / "data", tmp_path / "runs"
    (data / "circuit").mkdir(parents=True)
    (runs / "base" / "circuit").mkdir(parents=True)
    pairs = [{"id": f"p{i}", "lang": "en" if i % 2 else "bn", "n_tokens": 6, "attack_id": 7, "task_id": 8,
              "clean": f"1 2 {10 + i} {20 + i} 5 6", "corrupt": "1 2 30 31 5 6"} for i in range(6)]
    (data / "circuit" / "pairs_test.jsonl").write_text("\n".join(json.dumps(p) for p in pairs))
    scores = {"n_layers": L, "n_heads": H, "node_scores": {"A2.1": 0.5, "A1.0": 0.2, "A0.3": -0.1, "MLP 1": 0.3},
              "config": {"n_pairs": 6, "ig_steps": 1}, "logit_diff": {"clean": 0.1, "corrupt": -0.1}}
    (runs / "base" / "circuit" / "scores.json").write_text(json.dumps(scores))
    (runs / "base" / "circuit" / "sweep.json").write_text(json.dumps({"chosen_k": 2}))
    monkeypatch.setattr("sandesh.gen.load_model", lambda path: (_model(), _Tok()))

    C.patch("x", "base", data, runs, "base", None, 4, 3, False)
    res = json.loads((runs / "base" / "circuit" / "patching.json").read_text())
    assert res["k"] == 2 and res["n_pairs"] == 4
    assert set(res["sets"]) == {"top1", "top2", "all", "rand1", "rand2"}
    assert res["sets"]["rand2"]["n_sets"] == 3 and res["sets"]["rand1"]["n_sets"] == 1
    assert res["heads"]["top2"] == ["A2.1", "A1.0"]
    assert set(res["verdict"]) >= {"removed", "recreated", "pass"}
    # the scam reaches the decision token only through attention: swapping every head swaps the whole effect
    assert res["sets"]["all"]["removed"] == pytest.approx(1.0, abs=1e-4)
    assert res["sets"]["all"]["recreated"] == pytest.approx(1.0, abs=1e-4)
    rows = [json.loads(l) for l in (runs / "base" / "circuit" / "patching_pairs.jsonl").read_text().splitlines()]
    assert len(rows) == 4 and all(len(r["restore"]) == 1 + 1 + 1 + 3 + 1 for r in rows)

    md = "\n".join(circuit_markdown(circuit_summary(runs)))
    assert "Activation patching on 4 held-out test pairs" in md and "| 2 (chosen) |" in md
    assert "Pre-registered rule at k = 2" in md
