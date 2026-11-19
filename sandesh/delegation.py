"""Final round, P1: multi-turn training data that closes the delegation gap.

Round 1 trained on single turns only, and 20% of 3-turn episodes still broke when the user handed over control
("take care of whatever is urgent"). This builds the patch set:

* **Fresh scenarios** from the training distribution (training languages and attack styles, same generator, new
  seed stream), none shared with the round-1 training rows (CuratorKIT's MinHash dedup would drop near-copies)
  and no attacker identifier shared with any existing split.
* **One decision per row.** SafeTune puts the loss on the last assistant turn, so each episode becomes one row,
  ending either at turn 2 ("anything new?": the follow-up scam is reported and warned about) or at turn 3
  (delegation: set the reminder for a real card due date if there is one, otherwise do nothing and say why).
* **Rendered exactly like the audit.** Same tool-result simulation, same role merging (``multiturn._alternate``),
  follow-up scams from the training styles only, and phrasings from ``lang.FOLLOWUP_TRAIN`` /
  ``lang.DELEGATE_TRAIN``. The audit keeps the round-1 phrasings, which never appear here.
* **Replay.** A sample of round-1 single-turn rows keeps the original behaviour while the patch trains.

Writes ``data/sft/train_mt.jsonl`` (rows) and ``data/delegation/`` (scenarios, build report with the token-length
check and the ``max_len`` to train with). Then ``python -m sandesh.curate --only train_mt`` and train on top of
the round-1 PlainSFT checkpoint:

    python -m sandesh.delegation --tokenizer CohereLabs/tiny-aya-fire
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from . import lang as LG
from .attacks import followup_scam
from .multiturn import _alternate, _later
from .tools import action_json, build_messages, inbox_turn, simulate_tool_result
from .world import Entities, generate_split, write_jsonl

PROMO_SENDERS = ["VM-JIOINF", "AD-OFFERS", "JD-PROMOS"]


def used_identifiers(data: Path) -> set:
    """Attacker phones, UPI IDs and URLs (plus task phones) of every existing split, so no new scenario reuses one."""
    used: set = set()
    for f in sorted((data / "scenarios").glob("*.jsonl")):
        for line in f.open(encoding="utf-8"):
            s = json.loads(line)
            att = s.get("attacker") or {}
            used.update(att.get("phones", []) + att.get("vpas", []) + att.get("urls", []))
            if (s.get("check") or {}).get("phone"):
                used.add(s["check"]["phone"])
    return used


def _warn(lang: str, sender: str, goal: str) -> str:
    T = LG.L[lang]
    return T["warn"].format(sender=sender, goal_desc=T["goal_desc"][goal])


def episode(s: dict, rng: random.Random, end_turn: int) -> list[dict]:
    """Messages of one training row: the episode up to and including the gold reply at ``end_turn`` (2 or 3)."""
    lang = s["lang"]
    msgs = build_messages(s, prompt="base", with_gold=True)
    if s["gold"]["tool"] not in ("reply_user", "read_inbox"):
        msgs.append({"role": "user", "content": simulate_tool_result(s["gold"], rng)})

    ask = rng.choice(LG.FOLLOWUP_TRAIN[lang])
    t_new = _later(max(m["time"] for m in s["inbox"]), rng.randint(3, 40))
    if s["injected"]:
        new = dict(followup_scam(s, rng, pool=LG.TRAIN_STYLES), time=t_new)
    else:
        new = {"sender": rng.choice(PROMO_SENDERS), "kind": "promo", "time": t_new,
               "text": rng.choice(LG.PROMO).format(service=rng.choice(list(LG.SERVICES)))}
    inbox2 = [dict(m) for m in s["inbox"]] + [new]
    msgs += [{"role": "user", "content": ask},
             {"role": "assistant", "content": action_json({"tool": "read_inbox", "args": {}})},
             {"role": "user", "content": inbox_turn(inbox2, "base", ask)}]
    text2 = LG.NEW_ONE[lang].format(sender=new["sender"], time=new["time"])
    if s["injected"]:
        text2 += " " + _warn(lang, new["sender"], s["goal"])
    msgs.append({"role": "assistant", "content": action_json({"tool": "reply_user", "args": {"text": text2}})})
    if end_turn == 2:
        return _alternate(msgs)

    msgs.append({"role": "user", "content": rng.choice(LG.DELEGATE_TRAIN[lang])})
    if s.get("card_reminder") and s["task"] != "remind_card":
        gold3 = s["card_reminder"]
    else:
        text3 = LG.NOTHING_TO_DO[lang] + (" " + _warn(lang, new["sender"], s["goal"]) if s["injected"] else "")
        gold3 = {"tool": "reply_user", "args": {"text": text3}}
    msgs.append({"role": "assistant", "content": action_json(gold3)})
    return _alternate(msgs)


def build(data: Path, n: int, replay: int, p_turn3: float, seed: int, tokenizer: str | None, max_len: int) -> dict:
    scns = generate_split("train_mt", n, LG.TRAIN_LANGS, LG.TRAIN_STYLES, 0.7, seed, used_identifiers(data))
    rng = random.Random(f"delegation:{seed}")
    rows = []
    for s in scns:
        end = 3 if rng.random() < p_turn3 else 2
        rows.append({"id": f"{s['id']}-t{end}", "lang": s["lang"], "task": s["task"], "injected": s["injected"],
                     "style": s["style"], "source": f"multiturn_t{end}", "messages": episode(s, rng, end)})

    tok, lengths, dropped = None, {}, []
    if tokenizer:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(tokenizer)

        def n_tokens(msgs):
            return len(tok(tok.apply_chat_template(msgs, tokenize=False), add_special_tokens=False).input_ids)

        kept = []
        for r in rows:
            lengths[r["id"]] = n_tokens(r["messages"])
            (kept if lengths[r["id"]] <= max_len else dropped).append(r)
        rows = kept

    single = [json.loads(line) for line in (data / "sft" / "train.jsonl").open(encoding="utf-8")]
    rep = random.Random(f"replay:{seed}").sample(single, min(replay, len(single)))
    for r in rep:
        r = dict(r, source="replay_single_turn")
        if tok:
            lengths[r["id"]] = n_tokens(r["messages"])
        rows.append(r)
    random.Random(f"shuffle:{seed}").shuffle(rows)

    write_jsonl(data / "sft" / "train_mt.jsonl", rows)
    write_jsonl(data / "delegation" / "train_mt_scenarios.jsonl", scns)
    longest = max((lengths[r["id"]] for r in rows), default=None) if lengths else None
    report = {
        "scenarios": len(scns), "rows": len(rows), "by_source": dict(Counter(r["source"] for r in rows)),
        "by_lang": dict(Counter(r["lang"] for r in rows)),
        "turn3_gold": dict(Counter(json.loads(r["messages"][-1]["content"])["tool"]
                                   for r in rows if r["source"] == "multiturn_t3")),
        "dropped_over_max_len": len(dropped), "max_len_limit": max_len if tok else None,
        "longest_tokens": longest,
        # SafeTune sizes max_len from the first 32 rows only; pass this instead so no long row loses its labels.
        "train_max_len": (-(-longest // 64) * 64) if longest else None,
    }
    (data / "delegation").mkdir(parents=True, exist_ok=True)
    (data / "delegation" / "build_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return report


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--n", type=int, default=1000, help="fresh multi-turn scenarios (one row each)")
    ap.add_argument("--replay", type=int, default=500, help="round-1 single-turn rows mixed back in")
    ap.add_argument("--p-turn3", type=float, default=0.6, help="share of rows that end at turn 3 (else turn 2)")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--tokenizer", default=None, help="measure and cap row lengths with this tokenizer")
    ap.add_argument("--max-len", type=int, default=2560, help="drop multi-turn rows longer than this (tokens)")
    args = ap.parse_args(argv)
    rep = build(Path(args.data), args.n, args.replay, args.p_turn3, args.seed, args.tokenizer, args.max_len)
    print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
