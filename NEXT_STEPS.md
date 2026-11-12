# Handoff / status (keep this current; any new session should read it first)

**Hackathon:** Lexsi AI Safety & Alignment Hackathon, Track 2. Submission deadline **Nov 15 2026, 11:59 PM AoE
= Nov 16, 5:29 PM IST**. Finalists announced Nov 16; finalist video/slides due Nov 22 AoE.
Submit at https://hackathon.lexsi.ai/submission/ (needs: abstract < 500 words, HF model collection, HF dataset
collection, write-up link, GitHub link, repos + models used, track + problem statements).

**Idea:** see README. Scam-SMS prompt injection against an on-device Tiny Aya Fire SMS assistant; fix with SafeTune
SafeGrad; measured with exact checks incl. held-out languages (bn/ta/mr) and attack styles (honorific, fake tool JSON);
stress-tested with best-of-N rewrites, a 3-turn escalation, detectors, XSTest and Global-MMLU; CircuitKIT locates
the heads that carry the hijack and a head knockout tests them. Lexsi chain: CuratorKIT -> SafeTune -> AuditKIT, plus
CircuitKIT (all four Track 2 repos). Problem statements are listed by title in `SUBMISSION.md`.

**GPU box rule:** create folders only under `/media/NAS/ashank`. `scripts/env.sh` points every cache there.

## Done
- [x] Benchmark generator `sandesh/world.py` + templates `sandesh/lang.py`; label tests `tests/test_bench.py` (9 pass)
- [x] CuratorKIT stage, SafeTune train stage, evaluate, Qwen3Guard safety judge, AuditKIT scoring, figures, explorer, ROI, publish
- [x] `scripts/run_all.sh` (resumable, safe to `git pull` mid-run), `scripts/setup_gpu.sh`, `scripts/smoke_local.sh`
- [x] Add-on audits (all optional stages, after the core results):
  - spotlighting prompt (`--prompt spotlight`) and Qwen3Guard SMS filter (`sandesh/guard.py`, `--inbox-filter`)
  - detector recall / false alarms by language (Qwen3Guard strict + loose, ProtectAI DeBERTa)
  - best-of-N adaptive attack (`sandesh/attacks.py`, `sandesh/bon.py`), ASR@k curves
  - multi-turn escalation (`sandesh/multiturn.py`), scored with AuditKIT `agent_eval`
  - XSTest over-refusal (`benign.jsonl`), Global-MMLU en/hi/bn (`sandesh/capability.py`)
  - `sft_mix` ablation (PlainSFT with the refusal anchor mixed in)
  - CircuitKIT (`sandesh/circuit.py`): EAP-IG on scam vs same-length promo pairs, base vs SafeGrad; head-knockout
    sweep with a random-head control; `base_knockout` / `base_knockout_rand` checkpoints evaluated like any condition.
    CircuitKIT runs in its own venv `.venv-ck` (`scripts/setup_ck.sh`, created by run_all) since it pins hf-hub<2.
- [x] Transcript explorer (`results/explorer.html`, deployed as a static Space by `publish`): single-turn cards plus
      a "Multi-turn" tab (inbox, the scammer's follow-up SMS, each turn's action, "hijacked at turn n" vs "held").
- [x] Local CPU smoke test on SmolLM2-135M passes end to end (`SMOKE OK`), including every add-on and CircuitKIT.
      (The `RLock ... _recursion_count` traceback at exit is a harmless `multiprocess` shutdown message.)
- [x] `summary.md` ends with a significance table and a 26-row "Headline numbers" table; `SUBMISSION.md` uses
      `[fill #n]` = row n of that table. Abstract draft is < 500 words.

## To do (in order)
1. On the GPU box (first time):
   ```bash
   cd /media/NAS/ashank && git clone https://github.com/ashank-crazy/sandesh && cd sandesh
   bash scripts/setup_gpu.sh
   source scripts/env.sh && hf auth login        # accept licence at huggingface.co/CohereLabs/tiny-aya-fire first
   nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &
   tail -f logs/run_all.log
   ```
   On a 24GB 3090: `BS_TRAIN=2 BS_GEN=16 BS_MT=8 nohup bash scripts/run_all.sh > logs/run_all.log 2>&1 &`.
   **Already running an older clone?** Let it run; `git pull` is safe mid-run. Once that run has finished, start the
   same command again: finished stages are skipped (`.done/`), new stages run. `run_all.sh` refuses to start while
   another copy is running (it would fight the first for GPU memory); `NO_LOCK=1` overrides that.
   **Early check (~30-45 min in):** when `score_baselines` finishes, paste `results/summary.md` to Claude. If base
   attack success is near 0% or "Re-reads inbox" is high, fix the prompt format before training burns GPU hours.
   "CORE RESULTS READY" in the log means the main table exists; the add-ons follow (several more hours).
2. When done, paste `results/summary.md` + `grep -h "FAILED\|warn" logs/run_all.log` back to Claude. Fill README
   "Results" and the `[fill #n]`s in `SUBMISSION.md`. If results don't support the README title ("We fixed it") or a
   claim in the abstract (e.g. the knockout beats random heads), rewrite it honestly.
3. `python -m sandesh.roi --api-in <$> --api-out <$> --gpu-hourly <$>` with current prices.
4. `python -m sandesh.publish --user <hf-user>`: dataset, models, explorer Space, 2 collections.
5. Write HF article (or use README); abstract is drafted in `SUBMISSION.md`; submit form before Nov 16 17:29 IST.
6. If finalist: 3-min video using the explorer Space (multi-turn tab: show an episode where the base model breaks at
   turn 2 or 3 and SafeGrad holds; the explorer puts those first).

## If a stage fails
Every add-on is optional, so the run continues; its log is `logs/<stage>.log`. Re-run just that stage after a fix:
`bash scripts/run_all.sh <stage>` (e.g. `ck_discover_base`). Likely trouble spots:
- `ck_env`: CUDA wheel mismatch in `.venv-ck` (the script copies the main venv's torch build; check `logs/ck_env.log`).
- `ck_discover_*`: out of memory on a 3090 with long prompts. Use `CK_N=32`, or rebuild the pairs with
  `python -m sandesh.circuit pairs --model CohereLabs/tiny-aya-fire --max-tokens 1000`, then delete
  `.done/ck_discover_base` and re-run.
- `guard_detect`: Qwen3Guard is large; reduce `BS_GEN`.
