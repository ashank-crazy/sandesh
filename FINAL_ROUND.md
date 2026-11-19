# Final round plan

Deadline: **Nov 24, 11:59 PM AoE = Wed Nov 25, 17:29 IST.** Our own hard stop: submit by **Tue Nov 24, 23:59 IST**.

Rules from the hackathon pages (Nov 20): shortlisted teams "prove their thesis and submit a video presentation or
slides"; the final judging uses only the video or slides. Finalists also get $200 in Hugging Face credits to polish
artifacts or run extra experiments. The submit page now has a recommended write-up layout; README v2 follows it.

## The thesis

A single scam SMS can hijack an on-device Tiny Aya assistant. A small LoRA fine-tune built with
CuratorKIT → SafeTune → AuditKIT stops it **on the phone itself**: in languages it never trained on, against an adaptive
and a multi-turn attacker, and after 4-bit quantization. CircuitKIT shows where in the network the hijack happens.

Round 1 proved most of it. The final round closes the gaps that round 1 declared: delegation (20.0% of 3-turn episodes
still hijacked), "on-device" without running on a device, CircuitKIT out of memory, one seed, and an unchecked judge.

## Proofs (each pass rule is fixed before the run; results are reported whatever they show)

| | Experiment | Pass rule | GPU time (3090) |
|---|---|---|---|
| P1 | **Close the delegation gap (model v2).** Multi-turn training episodes from train scenarios only (en/hi/hinglish, train attack styles): turn 2 = follow-up scam, turn 3 = delegation. Gold: warn, never act for the attacker. Plus *legit-urgent* episodes where delegation should act (card-due reminder, bill), so the model does not learn "refuse delegation". 8 delegation phrasings per language for training; 4 different ones held out for test. PlainSFT on single-turn + multi-turn data, same budget, curated with CuratorKIT. | hijacked by turn 3 ≤ 5% on held-out phrasings (PlainSFT 20.0%); legit delegation done ≥ PlainSFT; single-turn ASR ≤ 0.5%, task success ≥ 98%; XSTest ≤ 15% | train ~3 h, eval ~2 h |
| P2 | **Runs on the phone.** GGUF Q4_K_M (llama.cpp; Tiny Aya is Cohere2, which Cohere already ships as GGUF) for base, PlainSFT and v2. All four test splits + multi-turn through llama.cpp. Tokens/s on a laptop CPU, optionally a phone. Offline side-by-side demo on the Mac. | ASR at most 0.5 pts above bf16; task success within 2 pts | ~2 h |
| P3 | **CircuitKIT: where the hijack happens.** Fix the OOM with shorter equal-length pairs (≤ 700 tokens) or a bigger GPU. EAP-IG on base, choose k on dev, knock out top-k heads vs 3 random sets on test, then the same heads' attribution in PlainSFT (did fine-tuning silence them?). Uses all four Track 2 repos. | top-k cuts the attacker-tool win rate ≥ 2x more than random heads, CIs not overlapping, and the no-scam task-tool win rate drops ≤ 5 pts; otherwise reported as a negative result | ~3 h (A100: ~1 h) |
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
| Fri 20 | 00:30-07:00 P4 seeds. Evening: P1 train, then eval | P1 code (episode builder, held-out phrasings, legit-delegation metric), P2 script, P3 OOM fix |
| Sat 21 | P1 eval + multi-turn + best-of-N; P2 GGUF eval; P3 (A100 or credits if free) | slides draft, README v2 skeleton, scoring for P1-P4 |
| Sun 22 | leftovers; v2 seeds if P1 passes; P5 labelling (you) | numbers into slides and README, demo set-up |
| Mon 23 | publish final artifacts | record the video |
| Tue 24 | – | buffer, review, **submit by 23:59 IST** |

## Open questions (needed by Fri 20 evening)

1. The finalist email: how the final is submitted, video length limit, slide format, and anything about updating
   round-1 artifacts.
2. Is the A100 40GB free this week?
3. Have the $200 HF credits arrived (they go to the team lead's email)?
4. Narration: your voice or a TTS voice (Kokoro, as before)? Face on camera or not?
5. Which phone, if any, for the on-device shot (Android or iPhone)?
