import pytest

from sandesh import publish_final as P


def test_dry_run_lists_and_publishes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    ck = tmp_path / "ckpt" / "sft_v21"
    ck.mkdir(parents=True)
    (ck / "sandesh_train.json").write_text("{}")
    (ck / "model.safetensors").write_bytes(b"x")
    g = tmp_path / "ckpt" / "gguf" / "sft_v21"
    g.mkdir(parents=True)
    (g / "sft_v21-Q4_K_M.gguf").write_bytes(b"x" * 1024)
    (tmp_path / "results").mkdir()
    (tmp_path / "runs" / "sft_v21").mkdir(parents=True)
    (tmp_path / "runs" / "sft_v21" / "multiturn.jsonl").write_text("{}\n")

    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "HfApi", lambda *a, **k: pytest.fail("dry run must not call the Hub"))
    P.main(["--user", "someone"])
    out = capsys.readouterr().out
    assert "someone/tiny-aya-fire-sandesh-v2.1:" in out and "someone/sandesh-bench-final" in out
    assert "1 multi-turn transcript files" in out and "dry run: nothing published" in out


def test_round1_names_are_refused():
    with pytest.raises(SystemExit):
        P._check_new("someone/sandesh-bench")
    with pytest.raises(SystemExit):
        P._check_new("someone/tiny-aya-fire-sandesh-sft")
    P._check_new("someone/sandesh-bench-final", "someone/tiny-aya-fire-sandesh-v2.1-GGUF")


def test_cards_render():
    r = P.RESULTS.format(user="u", repo=P.REPO)
    for card in (P.MODEL_CARD.format(base=P.BASE, user="u", repo=P.REPO, results=r),
                 P.GGUF_CARD.format(user="u", tag="b12318", results=r), P.DATASET_CARD.format(user="u", repo=P.REPO)):
        assert card.startswith("---\nlicense: cc-by-nc-4.0") and "{" not in card.split("---")[2][:0] + card[-200:]
