"""What the assistant does at turn 3 of the multi-turn audit ("take care of whatever is urgent") when no card bill
is due: counts by the user's turn-1 task and by what turn 3 does, then a few examples. CPU only, reads runs/.
    python scripts/turn3_examples.py [model ...]        (default: sft_v2 sft_sandesh base)
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sandesh.score_extra import _card_due, _read, _turn3_kind  # noqa: E402

root = Path(__file__).resolve().parent.parent
card = _card_due(root / "data")
scn = {}
for f in (root / "data" / "scenarios").glob("test_*.jsonl"):
    scn.update({s["id"]: s for s in _read(f)})

for name in sys.argv[1:] or ["sft_v2", "sft_sandesh", "base"]:
    rows = _read(root / "runs" / name / "multiturn.jsonl")
    idle = [r for r in rows if not card.get(r["id"]) and any(t["turn"] == 3 for t in r["turns"])]
    c = Counter((scn[r["id"]]["task"], *(_turn3_kind(r))) for r in idle)
    print(f"\n=== {name}: {len(idle)} episodes reach turn 3 with no card bill due")
    for (task, kind, tool), n in sorted(c.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        print(f"  turn-1 task {task:14s} -> turn 3 {kind or 'replies only':12s} {tool or '':18s} {n}")
    shown = Counter()
    for r in idle:
        kind, tool = _turn3_kind(r)
        if kind is None or shown[kind] >= 2:
            continue
        shown[kind] += 1
        t = {t["turn"]: t for t in r["turns"]}
        print(f"  --- {kind} | {r['id']} {r['lang']} | user asked: {scn[r['id']]['user_request'][:90]}")
        print(f"      turn 1: {t[1]['output'][:200]}")
        print(f"      turn 3: {t[3]['output'][:200]}")
