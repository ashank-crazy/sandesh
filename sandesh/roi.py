"""Cost of running the SMS assistant: closed API vs self-hosted GPU vs on-device.

Token counts and throughput are *measured* (runs/<cond>/perf.json, written by
sandesh.evaluate). Prices are inputs: pass your provider's current numbers,
because the defaults are placeholders, not quotes.

    python -m sandesh.roi --cond safegrad_sandesh --api-in 0.15 --api-out 0.60 --gpu-hourly 1.80
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--out", default="results")
    ap.add_argument("--cond", default="safegrad_sandesh")
    ap.add_argument("--api-name", default="closed small API model")
    ap.add_argument("--api-in", type=float, default=0.15, help="$ per 1M input tokens (PLACEHOLDER: set current price)")
    ap.add_argument("--api-out", type=float, default=0.60, help="$ per 1M output tokens (PLACEHOLDER)")
    ap.add_argument("--gpu-name", default="A100 40GB")
    ap.add_argument("--gpu-hourly", type=float, default=1.80, help="$ per GPU-hour (PLACEHOLDER)")
    ap.add_argument("--users", type=int, default=1_000_000)
    ap.add_argument("--req-per-user-day", type=float, default=10)
    args = ap.parse_args(argv)

    pf = Path(args.runs) / args.cond / "perf.json"
    if not pf.exists():  # fall back to any condition that has been evaluated (same model size)
        found = sorted(Path(args.runs).glob("*/perf.json"))
        if not found:
            raise SystemExit("no runs/*/perf.json yet")
        pf, args.cond = found[0], found[0].parent.name
    perf = json.loads(pf.read_text())
    tests = [v for k, v in perf.items() if k.startswith("test") and v.get("n")]
    n = sum(v["n"] for v in tests)
    p_tok = sum(v.get("prompt_tokens", 0) for v in tests) / n
    o_tok = sum(v["new_tokens"] for v in tests) / n
    secs = sum(v["seconds"] for v in tests)
    req_per_gpu_hour = n / secs * 3600
    device = tests[0].get("device", "?")

    api_per_req = (p_tok * args.api_in + o_tok * args.api_out) / 1e6
    gpu_per_req = args.gpu_hourly / req_per_gpu_hour
    daily = args.users * args.req_per_user_day
    rows = [
        (f"{args.api_name} (token billing)", api_per_req, api_per_req * daily * 30,
         "inbox (incl. OTPs) leaves the phone"),
        (f"Self-hosted Tiny Aya Fire on {args.gpu_name} (GPU-hours, HF generate, no batching server)",
         gpu_per_req, gpu_per_req * daily * 30, "inbox leaves the phone, goes to your server"),
        ("On-device Tiny Aya Fire (Q4, ~2 GB)", 0.0, 0.0, "inbox never leaves the phone"),
    ]
    md = [f"## Cost per request and per month ({args.users:,} users × {args.req_per_user_day:g} requests/day)", "",
          f"Measured on `{args.cond}` over {n} test requests on {device}: "
          f"{p_tok:.0f} prompt tokens and {o_tok:.0f} output tokens per request on average, "
          f"{req_per_gpu_hour:,.0f} requests per GPU-hour.", "",
          "| Deployment | $ / request | $ / month | Privacy |", "|---|---|---|---|"]
    for name, per, month, priv in rows:
        md.append(f"| {name} | {per:.6f} | {month:,.0f} | {priv} |")
    md += ["", f"Prices used (inputs, verify before quoting): API ${args.api_in}/1M in, ${args.api_out}/1M out; "
               f"GPU ${args.gpu_hourly}/hour. On-device marginal cost is zero; the user's phone pays in battery."]
    Path(args.out).mkdir(parents=True, exist_ok=True)
    (Path(args.out) / "roi.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
