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
import copy
import json
import random
from collections import Counter
from pathlib import Path

from . import lang as LG
from .attacks import followup_scam
from .multiturn import _alternate, _later
from .tools import action_json, build_messages, inbox_turn, simulate_tool_result
from .world import Entities, fmt_amt, generate_split, write_jsonl

PROMO_SENDERS = ["VM-JIOINF", "AD-OFFERS", "JD-PROMOS"]


def used_identifiers(data: Path, extra: tuple = ()) -> set:
    """Attacker phones, UPI IDs and URLs (plus task phones) of every existing split, so no new scenario reuses one.
    ``extra``: more scenario files (e.g. v2's delegation scenarios when building v2.1)."""
    used: set = set()
    for f in sorted((data / "scenarios").glob("*.jsonl")) + [Path(x) for x in extra if Path(x).exists()]:
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


# --------------------------------------------------------------------------- v2.1: with/without-card pairs
# v2 learned "delegated -> set a reminder": the right date in 59 of 59 audit episodes with a card bill due, but an
# invented reminder in 41 of 41 with none due (outside the remind_card task). Its rows were balanced (254 reminder vs
# 243 nothing-to-do), so balance was not enough. v2.1 trains on pairs: the same episode twice, once with the card-due
# SMS (gold: that reminder) and once with that SMS swapped for another message from the same bank that needs nothing
# done (gold: nothing needs doing). Same sender, position and time, same random draws, so that SMS is the only
# difference and the only cue. Plus natural no-card episodes, remind_card episodes (the reminder is already set),
# turn-2 rows and round-1 replay. Trained on top of v2.
NO_ACTION_BANK_SMS = [
    "{bank} Credit Card: Payment of Rs {amt} received. Thank you. Available limit Rs {limit}.",
    "{bank} Credit Card: Statement generated. No payment is due this month.",
    "{bank}: You are pre-approved for a personal loan up to Rs 5,00,000 at 10.5% p.a. Apply in the app. T&C apply.",
    "{bank}: Your credit card ending {last4} is now enabled for contactless payments.",
    "{bank}: Earn 5X reward points on dining this weekend with your credit card. T&C apply.",
]


def without_card(s: dict, rng: random.Random) -> dict:
    """The scenario with its card-due SMS replaced by a no-action message from the same bank (same sender, time and
    position, so a summary's sender list and count are unchanged)."""
    i = next(j for j, m in enumerate(s["inbox"]) if m["kind"] == "card")
    card = s["inbox"][i]
    bank = next(b for b in LG.BANKS if b in card["text"])
    text = rng.choice(NO_ACTION_BANK_SMS).format(
        bank=bank, amt=fmt_amt(rng.randint(20, 450) * 100), limit=fmt_amt(rng.randint(50, 400) * 1000),
        last4=rng.randint(1000, 9999))
    s2 = copy.deepcopy(s)
    s2["inbox"][i] = dict(card, text=text, kind="bank_no_action")
    s2["id"], s2["card_reminder"] = s["id"] + "-nocard", None
    return s2


def _jaccard3(a: str, b: str) -> float:
    ga, gb = {a[i:i + 3] for i in range(len(a) - 2)}, {b[i:i + 3] for i in range(len(b) - 2)}
    return len(ga & gb) / max(1, len(ga | gb))


def _dedup_text(msgs: list[dict]) -> str:
    """Roughly what CuratorKIT's MinHash compares for a conversation: every turn after the system prompt."""
    return "".join(m["content"] for m in msgs if m["role"] != "system")


def build_v21(data: Path, n_pairs: int, n_nocard: int, n_remind: int, n_t2: int, replay: int, seed: int,
              tokenizer: str | None, max_len: int) -> dict:
    used = used_identifiers(data, extra=(data / "delegation" / "train_mt_scenarios.jsonl",))
    pool = generate_split("train_mt21", 4 * (n_pairs + n_nocard + n_remind + n_t2), LG.TRAIN_LANGS, LG.TRAIN_STYLES,
                          0.7, seed, used)
    card = [s for s in pool if s["card_reminder"] and s["task"] != "remind_card"][:n_pairs]
    nocard = [s for s in pool if not s["card_reminder"] and s["task"] != "remind_card"][:n_nocard]
    remind = [s for s in pool if s["task"] == "remind_card"][:n_remind]
    taken = {s["id"] for s in card + nocard + remind}
    t2 = [s for s in pool if s["id"] not in taken][:n_t2]
    if len(card) < n_pairs:
        raise SystemExit(f"only {len(card)} card-due scenarios for {n_pairs} pairs")

    def rng_of(s):  # one stream per episode: both halves of a pair draw the same follow-up, phrasing and tool result
        return random.Random(f"delegation21:{seed}:{s['id']}")

    rows, pair_sim, scns = [], [], []
    for s in card:
        s2 = without_card(s, random.Random(f"nocard:{seed}:{s['id']}"))
        m1, m2 = episode(s, rng_of(s), 3), episode(s2, rng_of(s), 3)
        pair_sim.append(_jaccard3(_dedup_text(m1), _dedup_text(m2)))
        for x, m, src in ((s, m1, "pair_card"), (s2, m2, "pair_no_card")):
            rows.append({"id": f"{x['id']}-t3", "pair": s["id"], "lang": x["lang"], "task": x["task"],
                         "injected": x["injected"], "style": x["style"], "source": src, "messages": m})
        scns += [s, s2]
    for group, end, src in ((nocard, 3, "no_card"), (remind, 3, "remind_card"), (t2, 2, "turn2")):
        for s in group:
            rows.append({"id": f"{s['id']}-t{end}", "lang": s["lang"], "task": s["task"], "injected": s["injected"],
                         "style": s["style"], "source": src, "messages": episode(s, rng_of(s), end)})
            scns.append(s)

    tok, lengths, dropped = None, {}, []
    if tokenizer:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(tokenizer)

        def n_tokens(msgs):
            return len(tok(tok.apply_chat_template(msgs, tokenize=False), add_special_tokens=False).input_ids)

        for r in rows:
            lengths[r["id"]] = n_tokens(r["messages"])
        too_long = {r.get("pair") or r["id"] for r in rows if lengths[r["id"]] > max_len}
        dropped = [r for r in rows if (r.get("pair") or r["id"]) in too_long]  # a pair goes as a whole
        rows = [r for r in rows if (r.get("pair") or r["id"]) not in too_long]

    single = [json.loads(line) for line in (data / "sft" / "train.jsonl").open(encoding="utf-8")]
    for r in random.Random(f"replay21:{seed}").sample(single, min(replay, len(single))):
        r = dict(r, source="replay_single_turn")
        if tok:
            lengths[r["id"]] = n_tokens(r["messages"])
        rows.append(r)
    random.Random(f"shuffle21:{seed}").shuffle(rows)

    write_jsonl(data / "sft" / "train_mt21.jsonl", rows)
    write_jsonl(data / "delegation21" / "train_mt21_scenarios.jsonl", scns)
    longest = max((lengths[r["id"]] for r in rows), default=None) if lengths else None
    sims = sorted(pair_sim)
    report = {
        "rows": len(rows), "by_source": dict(Counter(r["source"] for r in rows)),
        "by_lang": dict(Counter(r["lang"] for r in rows)),
        "turn3_gold": dict(Counter(json.loads(r["messages"][-1]["content"])["tool"]
                                   for r in rows if r["source"] in ("pair_card", "pair_no_card", "no_card", "remind_card"))),
        # CuratorKIT drops near-copies (MinHash over character 3-grams, threshold 0.95): the two halves of a pair
        # must stay below it or one half would be dropped and the pair lost.
        "pair_char3_jaccard": {"min": sims[0], "median": sims[len(sims) // 2], "max": sims[-1]} if sims else None,
        "dropped_over_max_len": len(dropped), "max_len_limit": max_len if tok else None,
        "longest_tokens": longest,
        "train_max_len": (-(-longest // 64) * 64) if longest else None,
    }
    (data / "delegation21").mkdir(parents=True, exist_ok=True)
    (data / "delegation21" / "build_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
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
    ap.add_argument("--v21", action="store_true", help="v2.1 set: with/without-card pairs (see build_v21)")
    ap.add_argument("--pairs", type=int, default=300, help="v21: with/without-card pairs (2 rows each)")
    ap.add_argument("--no-card", type=int, default=150, help="v21: turn-3 rows with no card SMS at all")
    ap.add_argument("--remind", type=int, default=60, help="v21: turn-3 rows where the user already asked for it")
    ap.add_argument("--turn2", type=int, default=150, help="v21: turn-2 rows")
    args = ap.parse_args(argv)
    if args.v21:
        rep = build_v21(Path(args.data), args.pairs, args.no_card, args.remind, args.turn2,
                        300 if args.replay == 500 else args.replay, args.seed, args.tokenizer, args.max_len)
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return
    rep = build(Path(args.data), args.n, args.replay, args.p_turn3, args.seed, args.tokenizer, args.max_len)
    print(json.dumps(rep, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
