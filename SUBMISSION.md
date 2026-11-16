# Submission form answers (round 1)

Numbers are from the round-1 run (`results/summary.md`, Nov 16 07:11 IST). Still open: `⟦MT⟧` = the
"by turn 3" column of the "Multi-turn escalation" table in `results/summary.md` once the `mt_*` stages finish, and the
model collection link (printed at the end of `logs/publish.log` once the model upload finishes).

**Project:** Sandesh (संदेश): stopping scam-SMS prompt injection in an on-device multilingual assistant

**Track:** Track 2, AI Red Teaming, Safety and Alignment

**Problem statements** (by title): Adversarial and safety evaluation sets · Red-teaming and robustness evaluation
(best-of-N, encoding tricks, over-refusal) · Multi-turn audits (prompt injection in tools/documents, which turn
broke, reproducible transcripts) · Multilingual and code-mixed safety · Safety-preserving fine-tuning

**Lexsi repos used (three, chained; CircuitKIT analysis is running for the final round):**
- CuratorKIT: curation, exact + MinHash dedup, `sft_messages` export with provenance.
- SafeTune: `PlainSFTTrainer`, `SafeGradTrainer`.
- AuditKIT: precomputed runs, custom exact scorers, `compare().significance()` paired bootstrap, `agent_eval` on
  multi-turn episodes.

**Models:**
- Core: `CohereLabs/tiny-aya-fire`.
- Supplementary:
  - `Qwen/Qwen3Guard-Gen-4B`: safety judge for the harmful-prompt and over-refusal checks.
  - `HuggingFaceTB/SmolLM2-135M-Instruct`: CPU smoke tests only.

**Datasets used:**
- `CohereLabs/aya_redteaming`: anchor and harmful-prompt eval.
- `Paul/XSTest`: over-refusal.
- `CohereLabs/Global-MMLU`: capability retention.
- SandeshBench (ours).

**Links:**
- GitHub: https://github.com/ashank-crazy/sandesh
- Write-up: https://github.com/ashank-crazy/sandesh#readme
- HF model collection: [fill]
- HF dataset collection: https://huggingface.co/collections/ashank-crazy/sandesh-datasets-6afa6730d80aa334ca3be4f6
  (dataset: https://huggingface.co/datasets/ashank-crazy/sandesh-bench)
- Demo (transcript explorer Space): https://huggingface.co/spaces/ashank-crazy/sandesh-explorer

---

## Abstract (< 500 words)

Cohere's Tiny Aya runs offline on phones, and the natural on-device agent reads your SMS inbox and acts
for you. In India, the most common fraud arrives as an SMS. If one message in the inbox is a scam, does the
assistant obey it?

**SandeshBench** has 3,870 phone-inbox scenarios in English, Hindi, Hinglish, Bengali, Tamil and Marathi: seven
tools, seven everyday user tasks, and one SMS that tries to make the assistant forward an OTP, pay a UPI ID, open a
phishing link or call a fraud number, in seven attack styles. Labels are exact and LLM-free: a hijack is the
attacker's number, UPI ID or URL in the action's target field. Bengali, Tamil, Marathi and two attack styles are held
out of training.

Out of the box, Tiny Aya Fire obeys 14.0% of scam SMS (16.0% in held-out languages, 27.0% when the scam switches
script mid-message). Given 16 rewrites per scam (encodings, character noise, spoofed senders, urgency), the attacker
wins 52.1% of scenarios. A defensive system prompt lowers attack success to 4.3%, but task success on clean inboxes
falls from 48.3% to 38.8%.

We chain three Lexsi Track 2 repos:
- **CuratorKIT** gates, deduplicates and exports the training data with provenance.
- **SafeTune** fine-tunes Tiny Aya Fire (LoRA) to do the user's task, ignore the instruction and warn the user. We
  compare `PlainSFTTrainer`, `SafeGradTrainer` anchored to the base model's own refusals of Cohere's `aya_redteaming`
  prompts, and a control trained on the same inboxes with the scam removed.
- **AuditKIT** scores every transcript with exact scorers and paired-bootstrap significance, and audits multi-turn
  episodes with `agent_eval`.

Plain SFT brings attack success to 0.0% on all four test splits, unseen languages and attack styles included,
and to 0.0% under best-of-16 (95% CI 0-7.4%). Task success on clean inboxes rises from 48.3% to 99.5%, and it
warns the user in 94.9% of attacked replies. When the scammer follows up and the user delegates ("take care of
whatever is urgent"), ⟦MT⟧% of three-turn episodes are hijacked (base ⟦MT⟧%). General behavior holds:
unsafe answers on 400 held-out multilingual red-team prompts 4.0% (base 5.5%), XSTest over-refusal 12.4% (base
11.6%), Global-MMLU en/hi/bn 49.0% (base 48.0%).

Two findings we did not expect. First, the scam-free control already cuts attack success to 1.2%: much of the base
model's vulnerability comes from not knowing the task, not from a drive to obey. But the control never warns the
user and still falls for script-switched and fake tool-call scams; only training on the attacks closes the gap. Second,
SafeGrad was not needed: plain SFT did not erode general safety, so the anchor had nothing to protect. SafeGrad
kept harmful-prompt behavior at the base level (5.8% unsafe) but cost task success (95.7%) and warnings (78.9%), and
let 2.1% of best-of-16 attacks through.

We release the benchmark, every transcript, the models, the curated training sets, a transcript explorer and a
resumable one-command pipeline. The fix keeps the inbox on the phone: no OTP ever needs to
reach a cloud API.
