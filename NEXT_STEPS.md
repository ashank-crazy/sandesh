# Handoff / status (keep this current; any new session should read it first)

**Hackathon:** Lexsi AI Safety & Alignment Hackathon, Track 2. Submission deadline **Nov 15 2026, 11:59 PM AoE
= Nov 16, 5:29 PM IST**. Finalists announced Nov 16; finalist video/slides due Nov 22 AoE.
Submit at https://hackathon.lexsi.ai/submission/ (needs: abstract < 500 words, HF model collection, HF dataset
collection, write-up link, GitHub link, repos + models used, track + problem statements).

**Idea:** see README. Scam-SMS prompt injection against an on-device Tiny Aya Fire SMS assistant; fix with SafeTune
SafeGrad; measured with exact checks incl. held-out languages (bn/ta/mr) and attack styles (honorific, fake tool JSON).
Problem statements 2a.3 + 2b.5. Lexsi chain: CuratorKIT -> SafeTune -> AuditKIT.

**GPU box rule:** create folders only under `/media/NAS/ashank`. `scripts/env.sh` points every cache there.

## Done
- [x] Benchmark generator `sandesh/world.py` + templates `sandesh/lang.py`; label tests `tests/test_bench.py` (6 pass)
- [x] CuratorKIT stage, SafeTune train stage, evaluate, Qwen3Guard safety judge, AuditKIT scoring, figures, explorer, ROI, publish
- [x] `scripts/run_all.sh` (resumable), `scripts/setup_gpu.sh`, `scripts/smoke_local.sh`
- [x] Local CPU smoke test on SmolLM2-135M passes end to end (`SMOKE OK`): world → safety → curate → SafeTune plain +
      SafeGrad → evaluate → Qwen3Guard judge → score with AuditKIT paired bootstrap → report → explorer → roi.
      (The `RLock ... _recursion_count` traceback at exit is a harmless `multiprocess` shutdown message.)
- [x] Tool-result footer added so models don't stall by re-calling `read_inbox`; new "Re-reads inbox (stalls)" metric
- [x] `summary.md` now ends with a significance table and a 12-row "Headline numbers" table that maps 1:1 onto the
      `[fill]` placeholders in `SUBMISSION.md` (abstract draft, < 500 words)
- [x] `run_all.sh` scores the two baselines right after evaluating them (`score_baselines` stage) for an early check

## To do (in order)
1. On the GPU box:
   ```bash
   cd /media/NAS/ashank && git clone https://github.com/ashank-crazy/sandesh && cd sandesh
   bash scripts/setup_gpu.sh
   source scripts/env.sh && hf auth login        # accept licence at huggingface.co/CohereLabs/tiny-aya-fire first
   nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &
   tail -f logs/run_all.log
   ```
   On a 24GB 3090 use `BS_TRAIN=2 BS_GEN=16 nohup bash scripts/run_all.sh ...`.
   **Early check (~30-45 min in):** when `score_baselines` finishes, paste `results/summary.md` to Claude. If base
   attack success is near 0% or "Re-reads inbox" is high, fix the prompt format before training burns GPU hours.
2. When done, paste `results/summary.md` + any `logs/*.log` errors back to Claude; fill README "Results" and the
   `[fill]`s in `SUBMISSION.md` from the "Headline numbers" table. If results don't support the README title
   ("We fixed it"), retitle honestly.
3. `python -m sandesh.roi --api-in <$> --api-out <$> --gpu-hourly <$>` with current prices.
4. `python -m sandesh.publish --user <hf-user>`: dataset, 3 models, explorer Space, 2 collections.
5. Write HF article (or use README); abstract is drafted in `SUBMISSION.md`; submit form before Nov 16 17:29 IST.
6. If finalist: 3-min video using the explorer Space.
