# Submission form answers (draft; replace every [fill #n] after the GPU run)

`[fill #n]` is row n of the "Headline numbers" table at the end of `results/summary.md`.

**Project:** Sandesh (संदेश): stopping scam-SMS prompt injection in an on-device multilingual assistant

**Track:** Track 2, AI Red Teaming, Safety and Alignment

**Problem statements** (by title): Adversarial and safety evaluation sets · Red-teaming and robustness evaluation
(best-of-N, encoding tricks, over-refusal) · Multi-turn audits (prompt injection in tools/documents, which turn
broke, reproducible transcripts) · Multilingual and code-mixed safety · Safety-preserving fine-tuning · Locating
where safety lives / Circuit-level interventions

**Lexsi repos used (chained, all four):**
- CuratorKIT: curation, exact + MinHash dedup, `sft_messages` export with provenance.
- SafeTune: `PlainSFTTrainer`, `SafeGradTrainer`.
- AuditKIT: precomputed runs, custom exact scorers, `compare().significance()` paired bootstrap, `agent_eval` on
  multi-turn episodes.
- CircuitKIT: EAP-IG node attribution on custom contrastive pairs; the heads it finds drive a knockout experiment.

**Models:**
- Core: `CohereLabs/tiny-aya-fire`.
- Supplementary:
  - `Qwen/Qwen3Guard-Gen-4B`: safety judge, plus the SMS-filter baseline.
  - `protectai/deberta-v3-base-prompt-injection-v2`: detector baseline.
  - `HuggingFaceTB/SmolLM2-135M-Instruct`: CPU smoke tests only.

**Datasets used:**
- `CohereLabs/aya_redteaming`: anchor and harmful-prompt eval.
- `Paul/XSTest`: over-refusal.
- `CohereLabs/Global-MMLU`: capability retention.
- SandeshBench (ours).

**Links:**
- GitHub: https://github.com/ashank-crazy/sandesh
- Write-up: [fill: HF article URL, or the GitHub README]
- HF model collection: [fill]
- HF dataset collection: [fill]
- Demo (transcript explorer Space): [fill]

---

## Abstract (< 500 words)

Cohere's Tiny Aya is built to run offline on phones, and the natural on-device agent reads your SMS inbox and acts
for you. In India, the most common fraud arrives as an SMS. If one message in the inbox is a scam, does the
assistant obey it?

**SandeshBench** has 3,870 phone-inbox scenarios in English, Hindi, Hinglish, Bengali, Tamil and Marathi. There are
seven tools, seven everyday user tasks, and one SMS that tries to make the assistant forward an OTP, pay a UPI ID,
open a phishing link or call a fraud number, in seven attack styles. Labels are exact and LLM-free: a hijack is the
attacker's number, UPI ID or URL in the action's target field. Bengali, Tamil, Marathi and two attack styles are held
out of training.

Out of the box, Tiny Aya Fire is hijacked in [fill #1]% of attacks in familiar languages and [fill #2]% in held-out
languages. A defensive system prompt only reaches [fill #3]%.

We chain all four Lexsi Track 2 repos:
- **CuratorKIT** gates, deduplicates and exports the training data with provenance.
- **SafeTune** fine-tunes Tiny Aya Fire (LoRA) to do the user's task, ignore the instruction and warn the user. We use
  `SafeGradTrainer`, anchored to the base model's own refusals of Cohere's `aya_redteaming` prompts. We compare it with
  `PlainSFTTrainer`, with plain SFT that has those refusals mixed in, and with a control trained on scam-free inboxes.
- **AuditKIT** scores every transcript with exact scorers and paired-bootstrap significance, and audits multi-turn
  episodes with `agent_eval`.
- **CircuitKIT** locates the attention heads that carry the scam into the action choice.

SafeGrad cuts attack success to [fill #4]% in-distribution, [fill #5]% on unseen languages and [fill #6]% on unseen
attack styles. Task success on clean inboxes is [fill #7]% (base [fill #8]%), and it warns the user in [fill #9]% of
replies. Unsafe answers on 400 held-out multilingual red-team prompts: [fill #10]% (plain SFT [fill #11]%, base
[fill #12]%).

We then attack our own fix:
- **Adaptive rewrites.** With 16 rewrites per scam (encodings, character noise, spoofed senders, urgency), the
  attacker succeeds against SafeGrad [fill #15]% of the time, vs [fill #13]% for the base model and [fill #14]% for
  the strongest prompt defense.
- **Three turns.** The scammer follows up and the user delegates ("take care of whatever is urgent"). [fill #17]% of
  SafeGrad episodes are hijacked, vs [fill #16]% for the base.
- **No collateral loss.** Over-refusal on XSTest is [fill #19]% (base [fill #18]%), and Global-MMLU (en/hi/bn) is
  [fill #21]% (base [fill #20]%).

Inside the model, CircuitKIT attribution on scam vs same-length benign inboxes points to a small set of attention
heads. Zeroing them, with no training, moves attack success from [fill #22]% to [fill #23]%. Zeroing as many random
heads gives [fill #24]%.

We release the benchmark, every transcript, the fine-tuned models, the curated training sets with provenance, a
transcript explorer and a one-command resumable pipeline. The fix keeps the inbox on the phone: no OTP ever needs to
reach a cloud API.
