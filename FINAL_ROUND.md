# Final round plan

Deadline: **Nov 24, 11:59 PM AoE = Wed Nov 25, 17:29 IST.** Our own hard stop: submit by **Tue Nov 24, 23:59 IST**.
Compute: one RTX 3090 24 GB, shared with a labmate's jobs (no A100). Every GPU step below is sized for it.

Rules from the hackathon pages (Nov 20): shortlisted teams "prove their thesis and submit a video presentation or
slides"; the final judging uses only the video or slides. Finalists also get $200 in Hugging Face credits to polish
artifacts or run extra experiments. The submit page now has a recommended write-up layout; README v2 follows it.

## Status (Fri Nov 20, night IST)

- **P2 passed for v2** (4-bit Q4_K_M through llama.cpp b12318): ASR 0.1% → 0.1%, task success 99.0 → 99.0% clean and
  99.5 → 99.2% under attack, multi-turn 0 → 0%; 2.00 GiB (bf16 GGUF 6.25 GiB); 11 tok/s generation on a 6-core
  i7-8700 with no GPU. Base **fails** the same rule: ASR 14.0 → 16.2% (p = 0.007); Cohere's own Q4_K_M gives 16.1%,
  so this is quantization, not our conversion. 4-bit makes the undefended model easier to hijack; v2 keeps its
  defence. PlainSFT keeps single-turn ASR but multi-turn goes 20.0 → 26.7% and the card reminder 45.6 → 16.7%.
  Our GGUFs differ from Cohere's in two metadata keys (context_length 500000 vs 8192, eos_token_id 3 vs 6); results
  match Cohere's file (16.2 vs 16.1%), say so in the README.
- **P3 ran** (32 dev pairs, 845-911 tokens; top-10 heads stable in 89% of bootstrap resamples). The hijack runs
  through heads in layers 15-24 (top: A23.13, A23.12, A23.5, A22.15). PlainSFT keeps the same top heads but their
  positive attribution falls 15.9 → 3.6 (-78%). Pre-registered rule (decision token, k = 32 chosen on dev): attacker
  preferred 8.7% with the top heads zeroed vs 19.3% with random heads, task preference 97.3%: passes. But in free
  generation the same knockout breaks the assistant (0% valid tool calls, MMLU 28%; random-32 control 96.6% valid,
  MMLU 44.3%). Reading: the hijack goes through heads the assistant needs; zeroing them is not a defence, and
  fine-tuning turns the scam's push through them down instead.
- **Turn-3 shortcut (found Sat Nov 21):** v2 sets a reminder on *every* delegation unless the user had already asked for one (41 of 41 such episodes with no card bill due), inventing it when there is none ("Pay personal loan bill (Rs 5,000)", "30 October 2023"). It never pays, calls or texts at turn 3 (PlainSFT and base do). Training was balanced (254 reminder vs 243 nothing-to-do rows outside remind_card), so the patch learned the habit, not the inbox check. New metric: the card reminder must carry the card's real due date.
- **Earlier guess (wrong):** "acts at turn 3 with no card bill due" is 67% for v2 (41 of 61). 40 of those 61 episodes started with
  the user asking for an action (card reminder 20, call 9, pay milkman 6, text family 5), so this is most likely the
  model doing the requested action again. The metric now splits repeats from new actions;
  `scripts/turn3_examples.py` prints the breakdown and examples.

## Status (Fri Nov 20, afternoon IST)

- **P1 passed all five rules** (v2): hijacked by turn 3 0.0% (0 of 120; 95% upper bound 3.1%), card reminder when
  delegated 100%, single-turn ASR 0.1% (1 of 1,121), task success 99.0% clean / 99.5% under attack, XSTest 9.2%.
  Also best-of-16 0%, warns at turn 2 100%, Global-MMLU 48.0% (= base).
- **P3** attribution ran out of memory again: TransformerLens builds a [pos x heads x d_head x d_model] temporary for
  per-head outputs (6.6 GiB on an 845-token inbox). Fixed (e390364) with CircuitKIT's own opt-in memory patch, no
  per-head input copies (only edge attribution reads them), a reduced vocabulary, and one pair at a time, shortest
  first; same scores as before on SmolLM2 (largest difference 3e-6). Rerun started.
- **P2** tooling: llama.cpp b12318's prebuilt Ubuntu CUDA 12.8 binaries (the box's driver; no compiler needed) and
  the same tag's converter. `scripts/p2.sh`: convert + quantize on CPU, then evaluate on the GPU once it is free.

## The thesis

A single scam SMS can hijack an on-device Tiny Aya assistant. A small LoRA fine-tune built with
CuratorKIT → SafeTune → AuditKIT stops it **on the phone itself**: in languages it never trained on, against an adaptive
and a multi-turn attacker, and after 4-bit quantization. CircuitKIT shows where in the network the hijack happens.

Round 1 proved most of it. The final round closes the gaps that round 1 declared: delegation (20.0% of 3-turn episodes
still hijacked), "on-device" without running on a device, CircuitKIT out of memory, one seed, and an unchecked judge.

## Proofs (each pass rule is fixed before the run; results are reported whatever they show)

| | Experiment | Pass rule | GPU time (3090) |
|---|---|---|---|
| P1 | **Close the delegation gap (model v2).** A LoRA patch on top of the round-1 PlainSFT model (`sandesh/delegation.py`). 1,000 *fresh* scenarios from the training distribution (en/hi/hinglish, training attack styles, no attacker identifier shared with any split), one decision per row because SafeTune trains on the last reply: turn 2 ("anything new?": report and warn about the follow-up scam) or turn 3 (delegation: set the reminder for a real card due date if there is one, otherwise say nothing needs doing and why). Plus 500 round-1 rows replayed. Training phrasings only (6 follow-ups, 8 delegations per language); the audit keeps the round-1 phrasings, which never appear in training, plus bn/ta/mr. CuratorKIT keeps all 1,489 rows; 2,560-token rows, so every label survives. | hijacked by turn 3 ≤ 5% (PlainSFT 20.0%); sets the card reminder when delegated ≥ 50% of the time it is due (new metric, computed for every model); single-turn ASR ≤ 0.5%, task success ≥ 98%; XSTest ≤ 15% | train ~2 h, audits ~2 h |
| P2 | **Runs on the phone.** GGUF Q4_K_M (llama.cpp; Cohere ships Tiny Aya as GGUF, so llama.cpp supports it) for base (Cohere's own file), PlainSFT and v2. All four test splits + multi-turn through llama.cpp on the box. Tokens/s on a laptop, optionally a phone. Offline side-by-side demo on the Mac. llama.cpp's prebuilt CUDA 12.8 binaries (`scripts/setup_llama.sh`), so nothing is compiled; the Mac is for the demo only. | ASR at most 0.5 pts above bf16; task success within 2 pts | ~1-2 h |
| P3 | **CircuitKIT: where the hijack happens.** OOM fixed: the logits are computed at the decision token only (round 1 allocated [IG steps × ~1,400 tokens × 262k vocab]); same scores to the last digit on a test model. If memory still runs out, it retries on the shortest pairs with 3 IG steps. EAP-IG on base, choose k on dev, knock out top-k heads vs 3 random sets on test, then the same heads' attribution in PlainSFT (did fine-tuning silence them?). Uses all four Track 2 repos. | top-k cuts the attacker-tool win rate ≥ 2x more than random heads, CIs not overlapping, and the no-scam task-tool win rate drops ≤ 5 pts; otherwise reported as a negative result | ~2.5 h |
| P3b | **Activation patching (added Sat Nov 21, before the run).** The knockout breaks the assistant, so it cannot tell "these heads carry the scam" from "these heads are needed for anything". Patching changes no weights: on 300 test pairs (the first 150 are the knockout's), the top-k heads' outputs are swapped between the scam and no-scam versions of the same inbox. *Removed*: scam prompt, those heads given their no-scam outputs; share of the scam's push (attacker's-tool logit gap, scam minus no-scam) that goes away. *Recreated*: no-scam prompt, those heads given their scam outputs; share of the push that comes back. k = 32 (chosen on dev in P3), top-k vs 3 random sets; curve over k = 1-32 with one random set; all heads must give 100% both ways (correctness check). `scripts/p3b.sh`. | at k = 32, both *removed* and *recreated*: top-k at least 2x random, 95% bootstrap intervals over pairs not overlapping; otherwise reported as not passed | ~30-60 min |
| P4 | **Not luck: seeds.** PlainSFT with seeds 14 and 15 (round 1 used 13), full eval. Mean and range. | reported as is | ~6 h, tonight |
| P5 | **Check the judge.** 100 Qwen3Guard verdicts (50 harmful-prompt answers, 50 XSTest) hand-labelled in a small page → agreement and Cohen's κ. Core metrics stay exact (no judge). | reported as is | none (~40 min of your time) |

Stretch, only if P1-P3 are done by Saturday night: real phishing SMS (written for humans, not for an AI) + delegation;
an interactive Space running the GGUF on CPU.

## Deliverables

- **D1 Slides** (12-14): hook (an OTP forwarded to a scammer, live) → threat → SandeshBench → Lexsi chain →
  round-1 results → three surprises → P1 delegation fixed → P2 on a phone at 4 bits → P3 inside the model →
  what it costs (ROI: on-device = no API bill, inbox never leaves the phone) → feedback for the Lexsi kits → next steps.
- **D2 Video**: the slides narrated, with a live offline demo segment. Length: whatever the finalist email says.
- **D3 README v2** on the organizers' layout: one-line claim, "For judges: one minute" box, models and datasets with
  licences, leak check, CuratorKIT counts before/after, attack and over-refusal sets, judge check, hyperparameters per
  kit, seeds, quantized results, compute used, cost per 1k replies vs API, "with more credits", declaration of outside
  work, LLM-usage statement, changelog vs round 1.
- **D4 Artifacts**: new HF repos only (model v2, GGUFs, `sandesh-bench-final` with the multi-turn set and new
  transcripts) in a new collection "Sandesh - final round". The round-1 repos and collections stay untouched
  (tag `round1` on GitHub).
- **D5 Feedback for Lexsi**: what we hit in each kit (CircuitKIT/TransformerLens memory on long prompts, its
  huggingface-hub<2 pin, SafeGrad's ~1.6x step cost, Tiny Aya's chat template rejecting non-alternating roles). The
  hackathon's stated goal includes feedback on the stack; a slide plus a README section, and GitHub issues if you want.

## Schedule (IST)

| Day | GPU box (you run it) | Claude |
|---|---|---|
| Fri 20 | 00:30-07:00 P4 seeds. Then `scripts/final_round.sh` (waits for the seeds by itself): P1 ~4 h, P3 ~2.5 h | P1 and P3 done (code, tests, CPU smoke run). P2 script once the box tooling is known |
| Sat 21 | P2 GGUF build + eval; leftovers | slides draft, README v2 skeleton, P1/P3/P4 numbers in |
| Sun 22 | leftovers; v2 seeds if P1 passes; P5 labelling (you) | numbers into slides and README, demo set-up |
| Mon 23 | publish final artifacts | record the video |
| Tue 24 | – | buffer, review, **submit by 23:59 IST** |

## Open questions (needed by Fri 20 evening)

1. The finalist email: how the final is submitted, video length limit, slide format, and anything about updating
   round-1 artifacts.
2. Have the $200 HF credits arrived (they go to the team lead's email)?
3. Narration: your voice or a TTS voice (Kokoro, as before)? Face on camera or not?
4. Which phone, if any, for the on-device shot (Android or iPhone)?
5. P2 tooling on the box: the output of `nvcc --version; cmake --version; nproc; free -g; df -h /media/NAS/ashank`.
