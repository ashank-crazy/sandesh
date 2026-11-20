import json
import random

from sandesh import lang as LG
from sandesh.delegation import build, episode
from sandesh.tools import parse_action
from sandesh.world import generate_split, main as world_main


def _scns(n=60):
    return generate_split("train_mt", n, LG.TRAIN_LANGS, LG.TRAIN_STYLES, 0.7, 13, set())


def _roles_alternate(msgs):
    roles = [m["role"] for m in msgs]
    return roles[0] == "system" and all(a != b for a, b in zip(roles[1:], roles[2:]))


def test_episode_shape_and_gold():
    rng = random.Random(0)
    for s in _scns():
        for end in (2, 3):
            msgs = episode(s, rng, end)
            assert _roles_alternate(msgs) and msgs[-1]["role"] == "assistant"
            act = parse_action(msgs[-1]["content"])
            n_user = sum(m["role"] == "user" for m in msgs)
            assert n_user == (4 if end == 2 else 5)  # request, inbox, follow-up (+tool result), inbox 2, delegation
            if end == 2:
                assert act["tool"] == "reply_user"
                assert ("⚠️" in act["args"]["text"]) == s["injected"]
            elif s["card_reminder"] and s["task"] != "remind_card":
                assert act == s["card_reminder"]
            else:
                assert act["tool"] == "reply_user"
                assert act["args"]["text"].startswith(LG.NOTHING_TO_DO[s["lang"]])
                assert ("⚠️" in act["args"]["text"]) == s["injected"]
            # the audit's phrasings never appear in training rows
            text = json.dumps(msgs, ensure_ascii=False)
            assert LG.DELEGATE_USER[s["lang"]] not in text and LG.FOLLOWUP_USER[s["lang"]] not in text


def test_training_followups_use_training_styles_only(monkeypatch):
    import sandesh.attacks as A

    seen = []
    real = A.make_scam
    monkeypatch.setattr(A, "make_scam", lambda rng, ent, lang, style, *a, **k: (seen.append(style), real(rng, ent, lang, style, *a, **k))[1])
    rng = random.Random(0)
    for s in [s for s in _scns(200) if s["injected"]]:
        episode(s, rng, 2)
    assert seen and set(seen) <= set(LG.TRAIN_STYLES)


def test_build_avoids_existing_attackers(tmp_path):
    world_main(["--out", str(tmp_path), "--smoke"])
    build(tmp_path, n=40, replay=10, p_turn3=0.6, seed=13, tokenizer=None, max_len=2560)
    existing = set()
    for f in (tmp_path / "scenarios").glob("*.jsonl"):
        for line in f.open():
            a = json.loads(line)["attacker"]
            existing.update(a["phones"] + a["vpas"] + a["urls"])
    new = [json.loads(l) for l in (tmp_path / "delegation" / "train_mt_scenarios.jsonl").open()]
    for s in new:
        a = s["attacker"]
        assert not existing & set(a["phones"] + a["vpas"] + a["urls"])
    rows = [json.loads(l) for l in (tmp_path / "sft" / "train_mt.jsonl").open()]
    assert len(rows) == 50 and sum(r["source"] == "replay_single_turn" for r in rows) == 10
    rep = json.loads((tmp_path / "delegation" / "build_report.json").read_text())
    assert rep["rows"] == 50


def test_v21_pairs_differ_only_in_the_card_sms(tmp_path):
    from sandesh.delegation import build_v21

    world_main(["--out", str(tmp_path), "--smoke"])
    build(tmp_path, n=40, replay=10, p_turn3=0.6, seed=13, tokenizer=None, max_len=2560)  # v2's scenarios exist too
    rep = build_v21(tmp_path, n_pairs=20, n_nocard=8, n_remind=4, n_t2=6, replay=10, seed=13, tokenizer=None,
                    max_len=2560)
    rows = [json.loads(l) for l in (tmp_path / "sft" / "train_mt21.jsonl").open()]
    assert rep["rows"] == len(rows) == 2 * 20 + 8 + 4 + 6 + 10
    assert len({r["id"] for r in rows}) == len(rows)
    assert rep["pair_char3_jaccard"]["max"] < 0.95  # CuratorKIT would drop one half of a near-copy pair
    pairs = {}
    for r in rows:
        if r.get("pair"):
            pairs.setdefault(r["pair"], {})[r["source"]] = r["messages"]
    assert len(pairs) == 20
    for p in pairs.values():
        a, b = p["pair_card"], p["pair_no_card"]
        assert len(a) == len(b) and [m["role"] for m in a] == [m["role"] for m in b]
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x["content"] != y["content"]]
        assert diff[-1] == len(a) - 1 and len(diff) == 3  # inbox at turn 1, inbox at turn 2, the answer
        assert parse_action(a[-1]["content"])["tool"] == "set_reminder"
        nothing = parse_action(b[-1]["content"])
        assert nothing["tool"] == "reply_user" and any(nothing["args"]["text"].startswith(v)
                                                       for v in LG.NOTHING_TO_DO.values())
        for i in diff[:-1]:
            assert "Credit Card" in a[i]["content"] or "credit card" in a[i]["content"]
    for r in rows:
        if r["source"] in ("no_card", "remind_card"):
            assert parse_action(r["messages"][-1]["content"])["tool"] == "reply_user"
        text = json.dumps(r["messages"], ensure_ascii=False)
        assert LG.DELEGATE_USER[r["lang"]] not in text and LG.FOLLOWUP_USER[r["lang"]] not in text
    # no attacker identifier from any split or from v2's delegation scenarios
    old = set()
    for f in list((tmp_path / "scenarios").glob("*.jsonl")) + [tmp_path / "delegation" / "train_mt_scenarios.jsonl"]:
        for line in f.open():
            a = json.loads(line)["attacker"]
            old.update(a["phones"] + a["vpas"] + a["urls"])
    for line in (tmp_path / "delegation21" / "train_mt21_scenarios.jsonl").open():
        a = json.loads(line)["attacker"]
        assert not old & set(a["phones"] + a["vpas"] + a["urls"])
