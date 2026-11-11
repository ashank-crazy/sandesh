"""Static transcript explorer (one self-contained HTML file) from real eval transcripts.

Shows the phone inbox (scam highlighted) and what the base model and the
fine-tuned model actually did, side by side. Deploy as a static HF Space.

    python -m sandesh.explorer --before base --after safegrad_sandesh --out results/explorer.html
"""

from __future__ import annotations

import argparse
import html
import json
import random
from pathlib import Path

from .score import CONDITION_LABELS, SPLIT_LABELS, score_row
from .tools import parse_action
from .world import TEST_SPLITS

LANG = {"en": "English", "hi": "Hindi", "hinglish": "Hinglish", "bn": "Bengali", "ta": "Tamil", "mr": "Marathi"}


def _read(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.open(encoding="utf-8")]


def collect(data: Path, runs: Path, before: str, after: str, per_split: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    items = []
    for split in TEST_SPLITS:
        scns = {s["id"]: s for s in _read(data / "scenarios" / f"{split}.jsonl")}
        fb, fa = runs / before / f"{split}.jsonl", runs / after / f"{split}.jsonl"
        if not (fb.exists() and fa.exists()):
            continue
        ob = {r["id"]: r["output"] for r in _read(fb)}
        oa = {r["id"]: r["output"] for r in _read(fa)}
        rows = []
        for sid in ob.keys() & oa.keys():
            s = scns[sid]
            if not s["injected"]:
                continue
            sb, sa = score_row(s, ob[sid]), score_row(s, oa[sid])
            outcome = ("fixed" if sb["hijacked"] and not sa["hijacked"] else
                       "still_hijacked" if sa["hijacked"] else
                       "both_safe" if not sb["hijacked"] else "other")
            rows.append({
                "id": sid, "split": split, "split_label": SPLIT_LABELS[split], "lang": LANG[s["lang"]],
                "style": s["style"], "goal": s["goal"], "task": s["task"], "request": s["user_request"],
                "inbox": [{"sender": m["sender"], "time": m["time"], "text": m["text"], "scam": m["kind"] == "scam"}
                          for m in s["inbox"]],
                "before": {"raw": ob[sid], "action": parse_action(ob[sid]), **{k: sb[k] for k in ("hijacked", "success", "valid", "reread")}},
                "after": {"raw": oa[sid], "action": parse_action(oa[sid]), **{k: sa[k] for k in ("hijacked", "success", "valid", "reread")}},
                "outcome": outcome,
            })
        # Mostly wins, but keep failures visible: an honest explorer is a better demo.
        fixed = [r for r in rows if r["outcome"] == "fixed"]
        rest = [r for r in rows if r["outcome"] != "fixed"]
        rng.shuffle(fixed)
        rng.shuffle(rest)
        k_fixed = min(len(fixed), int(per_split * 0.7))
        items += fixed[:k_fixed] + rest[: per_split - k_fixed]
    return items


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sandesh Explorer</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700&family=Noto+Sans+Devanagari:wght@400;600&family=Noto+Sans+Bengali:wght@400;600&family=Noto+Sans+Tamil:wght@400;600&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>
:root{--bg:#f6f5f1;--surface:#ffffff;--surface-2:#efeee9;--ink:#1f1f1e;--ink-2:#5c5b55;--ink-3:#8a897f;--line:#e2e1db;
--accent:#2a78d6;--bad:#c0392b;--bad-bg:#fdecea;--good:#18794e;--good-bg:#e7f6ee;--scam:#c0392b;--scam-bg:#fff4f2;--warn-bg:#fff7e0;
--bubble:#dcecff;--radius:14px;--font:"Noto Sans","Noto Sans Devanagari","Noto Sans Bengali","Noto Sans Tamil",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#121211;--surface:#1c1c1b;--surface-2:#262624;--ink:#f0efec;--ink-2:#c3c2b7;--ink-3:#8f8e85;--line:#33332f;
--accent:#3987e5;--bad:#ff7b6b;--bad-bg:#3a1f1b;--good:#4cc38a;--good-bg:#16301f;--scam:#ff7b6b;--scam-bg:#2c1c19;--warn-bg:#2f2814;--bubble:#1f3550}}
:root[data-theme="dark"]{--bg:#121211;--surface:#1c1c1b;--surface-2:#262624;--ink:#f0efec;--ink-2:#c3c2b7;--ink-3:#8f8e85;--line:#33332f;
--accent:#3987e5;--bad:#ff7b6b;--bad-bg:#3a1f1b;--good:#4cc38a;--good-bg:#16301f;--scam:#ff7b6b;--scam-bg:#2c1c19;--warn-bg:#2f2814;--bubble:#1f3550}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 var(--font)}
.wrap{max-width:1120px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:28px;margin:0 0 6px;letter-spacing:-.01em}.sub{color:var(--ink-2);margin:0 0 20px;max-width:760px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:0 0 22px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.stat .k{color:var(--ink-2);font-size:13px}.stat .v{font-size:22px;font-weight:700;margin-top:2px}.stat .v small{font-size:13px;color:var(--ink-3);font-weight:400}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px;align-items:center}
select,button{font:inherit;font-size:14px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:7px 10px}
button{cursor:pointer}.count{color:var(--ink-3);font-size:13px;margin-left:auto}
.card{display:grid;grid-template-columns:minmax(0,380px) minmax(0,1fr);gap:18px;background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:16px;margin-bottom:16px}
@media (max-width:820px){.card{grid-template-columns:1fr}}
.phone{background:var(--surface-2);border-radius:16px;padding:12px}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}.tag{font-size:12px;color:var(--ink-2);background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:2px 8px}
.req{background:var(--bubble);border-radius:14px 14px 4px 14px;padding:8px 11px;margin:0 0 10px auto;max-width:92%;width:fit-content}
.sms{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:8px 10px;margin-bottom:7px;overflow-wrap:anywhere}
.sms .from{font-size:12px;color:var(--ink-3);display:flex;justify-content:space-between;gap:8px}
.sms.scam{border:1.5px solid var(--scam);background:var(--scam-bg)}.sms.scam .from b{color:var(--scam)}
.sms .t{white-space:pre-wrap;font-size:14px}
.side h3{font-size:13px;color:var(--ink-2);margin:0 0 6px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.act{border-radius:12px;padding:10px 12px;margin-bottom:12px;border:1px solid var(--line)}
.act.bad{background:var(--bad-bg);border-color:var(--bad)}.act.good{background:var(--good-bg);border-color:var(--good)}
.verdict{font-weight:700;font-size:14px;margin-bottom:6px;display:flex;gap:6px;align-items:center}
.act.bad .verdict{color:var(--bad)}.act.good .verdict{color:var(--good)}
pre{margin:0;font:12.5px/1.45 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink)}
.empty{color:var(--ink-3);padding:30px;text-align:center}
footer{color:var(--ink-3);font-size:13px;margin-top:28px}
a{color:var(--accent)}
</style>
</head>
<body>
<div class="wrap">
  <h1>Sandesh Explorer</h1>
  <p class="sub">Real transcripts from SandeshBench. Each card is a phone inbox with one scam SMS (red). The user asked for something ordinary;
  the scam tries to make the on-device assistant forward an OTP, pay a UPI ID, open a link or call a number. Left model: __BEFORE__. Right: __AFTER__.</p>
  <div class="stats" id="stats"></div>
  <div class="filters">
    <select id="f-split"><option value="">All test splits</option></select>
    <select id="f-lang"><option value="">All languages</option></select>
    <select id="f-style"><option value="">All attack styles</option></select>
    <select id="f-out"><option value="">All outcomes</option><option value="fixed">Hijacked → fixed</option><option value="still_hijacked">Still hijacked</option><option value="both_safe">Both safe</option></select>
    <button id="theme" aria-label="Toggle theme">◐ Theme</button>
    <span class="count" id="count"></span>
  </div>
  <div id="list"></div>
  <footer>Phone numbers, UPI IDs and links are randomly generated and fake. Code and data: <a href="__REPO__">__REPO__</a></footer>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const items = D.items, $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const STYLE = {direct:'Direct order', fake_system:'Fake system msg', authority:'Bank / RBI / police', owner_impersonation:'Owner impersonation',
  script_switch:'Script switch', honorific:'Honorific (held out)', fake_tool_json:'Fake tool JSON (held out)'};
const GOAL = {exfil_otp:'steal OTP', pay_attacker:'UPI payment', phish_link:'phishing link', call_attacker:'scam call'};
function fill(id, vals, label){ const el=$(id); [...new Set(vals)].sort().forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=label?label(v):v;el.appendChild(o)}) }
fill('#f-split', items.map(i=>i.split), v => items.find(i=>i.split===v).split_label);
fill('#f-lang', items.map(i=>i.lang)); fill('#f-style', items.map(i=>i.style), v=>STYLE[v]||v);
$('#stats').innerHTML = D.stats.map(s=>`<div class="stat"><div class="k">${esc(s.k)}</div><div class="v">${esc(s.v)} <small>${esc(s.sub||'')}</small></div></div>`).join('');
function verdict(r){
  if (r.hijacked) return ['bad','✕ Hijacked: obeyed the scam'];
  if (r.success) return ['good','✓ Did the user\'s task, ignored the scam'];
  if (!r.valid) return ['', '– No valid tool call'];
  if (r.reread) return ['', '– Stalled: asked to read the inbox again'];
  return ['', '– Ignored the scam, but missed the task'];
}
function act(label, r){
  const [cls, v] = verdict(r);
  const body = r.action ? JSON.stringify(r.action, null, 2) : r.raw;
  return `<div class="act ${cls}"><div class="verdict">${esc(v)}</div><h3>${esc(label)}</h3><pre>${esc(body)}</pre></div>`;
}
function render(){
  const f = {split:$('#f-split').value, lang:$('#f-lang').value, style:$('#f-style').value, out:$('#f-out').value};
  const shown = items.filter(i => (!f.split||i.split===f.split)&&(!f.lang||i.lang===f.lang)&&(!f.style||i.style===f.style)&&(!f.out||i.outcome===f.out));
  $('#count').textContent = `${shown.length} of ${items.length} transcripts`;
  $('#list').innerHTML = shown.length ? shown.map(i => `
    <article class="card">
      <div class="phone">
        <div class="tags"><span class="tag">${esc(i.lang)}</span><span class="tag">${esc(STYLE[i.style]||i.style)}</span><span class="tag">goal: ${esc(GOAL[i.goal]||i.goal)}</span><span class="tag">${esc(i.split_label)}</span></div>
        <div class="req">${esc(i.request)}</div>
        ${i.inbox.map(m=>`<div class="sms ${m.scam?'scam':''}"><div class="from"><b>${esc(m.sender)}</b><span>${m.scam?'scam · ':''}${esc(m.time)}</span></div><div class="t">${esc(m.text)}</div></div>`).join('')}
      </div>
      <div class="side">${act(D.before, i.before)}${act(D.after, i.after)}</div>
    </article>`).join('') : '<div class="empty">No transcripts match these filters.</div>';
}
['#f-split','#f-lang','#f-style','#f-out'].forEach(s=>$(s).addEventListener('change', render));
$('#theme').addEventListener('click', ()=>{ const r=document.documentElement; const dark = r.dataset.theme ? r.dataset.theme==='dark' : matchMedia('(prefers-color-scheme: dark)').matches; r.dataset.theme = dark?'light':'dark'; });
render();
</script>
</body>
</html>
"""


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--results", default="results")
    ap.add_argument("--before", default="base")
    ap.add_argument("--after", default="safegrad_sandesh")
    ap.add_argument("--per-split", type=int, default=40)
    ap.add_argument("--repo-url", default="https://github.com/ashank-crazy/sandesh")
    ap.add_argument("--out", default="results/explorer.html")
    args = ap.parse_args(argv)

    items = collect(Path(args.data), Path(args.runs), args.before, args.after, args.per_split, 13)
    stats = []
    mpath = Path(args.results) / "metrics.json"
    if mpath.exists():
        m = json.loads(mpath.read_text())["conditions"]
        for split in TEST_SPLITS:
            b = m.get(args.before, {}).get("splits", {}).get(split, {}).get("asr", {}).get("rate")
            a = m.get(args.after, {}).get("splits", {}).get(split, {}).get("asr", {}).get("rate")
            if b is not None and a is not None:
                stats.append({"k": f"Scam success · {SPLIT_LABELS[split]}", "v": f"{100 * b:.0f}% → {100 * a:.0f}%",
                              "sub": "before → after"})
    payload = {"items": items, "stats": stats,
               "before": CONDITION_LABELS.get(args.before, args.before),
               "after": CONDITION_LABELS.get(args.after, args.after)}
    page = (PAGE.replace("__DATA__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__BEFORE__", html.escape(payload["before"])).replace("__AFTER__", html.escape(payload["after"]))
            .replace("__REPO__", html.escape(args.repo_url)))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(page, encoding="utf-8")
    print(f"explorer: {len(items)} transcripts -> {args.out}")


if __name__ == "__main__":
    main()
