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

## Status (Nov 15, 18:45 IST) and the two-round plan
- Run started 16:32 IST on the 3090 (`FAST=1`, `BS_GEN=16`). Two other jobs share that GPU (`latest_virtenv/bin/python3.10`,
  5.2 GB) and generation ran ~2x slower after the first 10 min (base test_iid 21 s/batch, then ~41-45 s/batch).
- Fixes pushed for that: generation halves its batch by itself on CUDA OOM (so `BS_GEN=32 BS_MT=16` is safe and ~2x
  faster on a contended GPU); SafeGrad reads its KL reference through the LoRA model with adapters off instead of
  loading a second 6.7 GB copy (identical logits, checked; without it SafeGrad needs ~22 GB and would OOM next to
  the other jobs); `expandable_segments` allocator; add-ons reordered by value per GPU-hour.
- **Round 1 (due Nov 16 17:29 IST):** core results + the round-1 add-ons (capability, XSTest, multi-turn and best-of-N
  on base / SafeGrad / PlainSFT). The log prints "ROUND-1 RESULTS READY" once they are scored. Submit those.
  Plan the cutoff ~12:00-13:00 IST Nov 16 whatever happens: score/report/explorer/roi are CPU-only and can run
  alongside the GPU run (command below), so round 1 never waits on the heavy stages.
- **Final (video/slides due Nov 22 AoE):** the run keeps going after submission: CircuitKIT discovery + head knockout,
  spotlight and guard-filter baselines, the `sft_mix` ablation. Freeze round 1 first (`git tag round1`), then add these
  to the write-up, slides and video. With days of GPU time, a non-FAST rerun (2 epochs) is possible too.
- Results so far, any time, without stopping the run (CPU only):
  ```bash
  source scripts/env.sh && python -m sandesh.score && python -m sandesh.report && python -m sandesh.explorer && python -m sandesh.roi
  ```
- Early check passed (18:57 IST): base attack success 12.5% familiar / 16.0% held-out languages (14.0% all test
  splits; script-switch scams 27.0%); defensive prompt 4.3% but clean-inbox task success 48.3% -> 38.8%; 0% inbox
  re-reads, 98.7% valid tool calls. Restarted 18:57 IST on 1cf5772 with `BS_GEN=32 BS_MT=16` (only ~0-20% faster:
  generation is GPU-bound, not overhead-bound). `train_sft_clean` started 19:20 IST. Baseline numbers are filled
  in `SUBMISSION.md`; `⟦R1: ...⟧` markers there say what to keep depending on which add-ons finish.
- Training times on the shared 3090 (1 epoch, 1,200 steps at batch 2): `train_sft_clean` 2h10m (19:20-21:30),
  `train_sft_sandesh` 1h58m (21:30-23:29). `train_safegrad_sandesh` started 23:29 IST. Each SafeGrad step adds a
  forward+backward on a shorter (~700-token) safety batch and a no-grad base pass, so expect ~1.4-1.7x plain SFT:
  done ~02:15-03:00 IST. Then three core evals (~50-70 min each) + judge -> "CORE RESULTS READY" ~05:30-07:00;
  round-1 add-ons (~2.5-3 h) -> "ROUND-1 RESULTS READY" ~08:00-10:00 IST. Training pads every batch to a fixed
  length, so memory is the same at every step: if SafeGrad got past its first logged steps, it will not OOM later.
  Progress and the trainer's own ETA: `tail -c 600 logs/train_safegrad_sandesh.log | tr '\r' '\n' | tail -2`.

### Round-1 status (Nov 16, ~08:00 IST)
- Core + round-1 add-ons finished 07:11 IST. PlainSFT: 0.0% attack success on every split, 0/48 under best-of-16,
  99.5% clean task success, 94.9% warnings, no general-safety or MMLU loss. SafeGrad: 0.4%, 2.1% best-of-16, 95.7%
  task success, 78.9% warnings. Scam-free control: 1.2%. README Results and `SUBMISSION.md` are rewritten around
  this (plain SFT is the headline, SafeGrad an honest "not needed here").
- All three `mt_*` stages failed: Tiny Aya's chat template rejects two user messages in a row (tool result + the
  user's follow-up). Fixed in 29ee3d0 (merge same-role neighbours); run_all restarted to redo them first.
  When they finish: fill the `⟦MT⟧` markers in README and `SUBMISSION.md` from the "Multi-turn escalation" table.
- CircuitKIT discovery OOMed on the shared 3090 (TransformerLens attention patterns for ~1,400-token pairs need
  >18 GB). Final-round fix: shorter pairs (`pairs --max-tokens`), or the A100. Sweep/knockout failed only because
  discovery produced no scores.

### Round 1 done (Nov 16, ~09:00 IST)
- Multi-turn (fixed): hijacked by turn 3 base 67.5%, PlainSFT 20.0%, SafeGrad 24.2% (PlainSFT 2.5% by turn 2,
  warns 88.3%). Delegation at turn 3 is the weak spot: training data is single-turn.
- Published and checked public, un-gated: models collection https://huggingface.co/collections/ashank-crazy/sandesh-models
  (sft, safegrad, sft-clean), datasets collection .../sandesh-datasets, Space sandesh-explorer. Tag `round1`.
- Final round (video/slides due Nov 22 AoE): CircuitKIT discovery without the OOM (shorter pairs or the A100),
  spotlight/guard/sft_mix results (run_all is producing them), and a multi-turn training set for delegation.

### Round-1 morning checklist (Nov 16)
1. `grep ">>>\|<<<\|FAILED\|READY" logs/run_all.log | tail -25` on the box. "ROUND-1 RESULTS READY" = round-1 add-ons
   scored. If it is not there by ~12:00 IST, run the CPU-only results command above (the run keeps going).
2. Paste `results/summary.md` and that grep to Claude: fills README "Results" + `SUBMISSION.md`, fixes any claim the
   numbers do not support (README title "We fixed it", "No collateral loss"), resolves the `⟦R1⟧` markers, pushes.
3. ROI with current prices: `python -m sandesh.roi --api-in <$/M in> --api-out <$/M out> --gpu-hourly <$/h>`.
4. Publish from the box by ~13:00 IST (uploads ~20 GB of models; only finished checkpoints are uploaded, so it is safe
   while the run continues): `source scripts/env.sh && python -m sandesh.publish --user ashank-crazy`.
   Put the printed collection, Space and dataset links into `SUBMISSION.md`.
5. Claude tags the repo `round1` (README on GitHub is the write-up). Submit https://hackathon.lexsi.ai/submission/
   before 17:29 IST with the answers in `SUBMISSION.md`.

## To do (in order)
0. Restart the 18:00 run with the new settings (do it right after `<<< score_baselines done`, a stage boundary;
   finished stages are skipped, and `>>` keeps the old log lines for timing):
   ```bash
   pkill -f scripts/run_all.sh; pkill -f "python -m sandesh"; git pull
   FAST=1 BS_TRAIN=2 BS_GEN=32 BS_MT=16 nohup bash scripts/run_all.sh >> logs/run_all.log 2>&1 &
   ```
1. On the GPU box (first time):
   ```bash
   cd /media/NAS/ashank && git clone https://github.com/ashank-crazy/sandesh && cd sandesh
   bash scripts/setup_gpu.sh                    # prints a lot and ends with "SETUP OK"
   ```
   Hugging Face from a CLI-only box: in any browser (a phone is fine), on the same HF account, accept the licence at
   https://huggingface.co/CohereLabs/tiny-aya-fire (auto-approved; it is the only gated repo we use) and create a
   **Write** token at https://huggingface.co/settings/tokens (Write: `publish` uploads with it later). Then paste it
   at the prompt (nothing shows while you paste; answer `n` to "Add token as git credential?"):
   ```bash
   source scripts/env.sh && hf auth login
   hf auth whoami && hf download CohereLabs/tiny-aya-fire config.json > /dev/null && echo "Tiny Aya access OK"
   FAST=1 BS_TRAIN=2 BS_GEN=32 BS_MT=16 nohup bash scripts/run_all.sh >> logs/run_all.log 2>&1 &
   tail -f logs/run_all.log
   ```
   Drop `BS_TRAIN=2` on the A100 (40GB). The first log line prints the settings in use. If generation runs out of
   GPU memory it halves its batch and says so in the log (`batch size -> 16`); nothing to do.
   **`FAST=1`** is the deadline profile: same conditions and test sets, 1 training epoch (1,200 steps at batch 2),
   best-of-N on 8 scenarios per language (still 16 rewrites each), 20 multi-turn episodes per language, 100 MMLU
   questions, 32 CircuitKIT pairs, knockout sweep on 150 test pairs. Without it the run is roughly 1.5-2x longer.
   **Already running an older clone?** Let it run; `git pull` is safe mid-run. Once that run has finished, start the
   same command again: finished stages are skipped (`.done/`), new stages run. `run_all.sh` refuses to start while
   another copy is running (it would fight the first for GPU memory); `NO_LOCK=1` overrides that.
   **Early check (~30-45 min in):** when `score_baselines` finishes, paste `results/summary.md` to Claude. If base
   attack success is near 0% or "Re-reads inbox" is high, fix the prompt format before training burns GPU hours.
   "CORE RESULTS READY" in the log means the main table exists; "ROUND-1 RESULTS READY" adds capability, XSTest,
   multi-turn and best-of-N; the heavier add-ons (CircuitKIT, stronger baselines, mixing ablation) follow.
   **Out of time?** Stop the run and build the results from whatever finished (missing add-ons show as "–"):
   ```bash
   pkill -f scripts/run_all.sh; pkill -f "python -m sandesh"
   bash scripts/run_all.sh judge score report explorer roi
   ```
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
- Setup says `CUDA not visible`, or `run_all.sh` stops at `NO GPU`: torch does not match the driver. Re-run
  `bash scripts/setup_gpu.sh`; it reads the driver's CUDA version from `nvidia-smi` and takes torch from the cu126
  index on 12.x drivers (PyPI's torch is built for CUDA 13.x). The GPU box's driver is CUDA 12.8.
- `ck_env`: CUDA wheel mismatch in `.venv-ck` (the script copies the main venv's torch build; check `logs/ck_env.log`).
- `ck_discover_*`: out of memory on a 3090 with long prompts. Use `CK_N=32`, or rebuild the pairs with
  `python -m sandesh.circuit pairs --model CohereLabs/tiny-aya-fire --max-tokens 1000`, then delete
  `.done/ck_discover_base` and re-run.
- `guard_detect`: Qwen3Guard is large; generation halves its batch on OOM, so this should not fail on memory.
- A training stage out of memory (only training has no automatic fallback): free GPU memory (`nvidia-smi` shows
  other jobs), or restart with `BS_TRAIN=1`; finished stages are skipped. SafeGrad no longer loads a second model copy
  (`--reference-copy` brings that back), so it needs about what plain SFT needs.
