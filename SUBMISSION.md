# Submission form answers (draft; replace every [fill] after the GPU run)

**Project:** Sandesh (संदेश): stopping scam-SMS prompt injection in an on-device multilingual assistant

**Track:** Track 2, AI Red Teaming, Safety and Alignment
**Problem statements:** 2a.3 Multi-turn audits (injection hidden in tools/documents, reproducible transcripts) ·
2b.5 Safety-preserving fine-tuning

**Lexsi repos used (chained):** CuratorKIT (curation, dedup, provenance export) → SafeTune (`PlainSFTTrainer`,
`SafeGradTrainer`) → AuditKIT (precomputed runs, custom exact scorers, `compare().significance()` paired bootstrap)

**Models:** core `CohereLabs/tiny-aya-fire`. Supplementary: `Qwen/Qwen3Guard-Gen-4B` (safety judge only) and
`HuggingFaceTB/SmolLM2-135M-Instruct` (CPU smoke tests only).

**Links:**
- GitHub: https://github.com/ashank-crazy/sandesh
- Write-up: [fill: HF article URL, or the GitHub README]
- HF model collection: [fill]
- HF dataset collection: [fill]
- Demo (transcript explorer Space): [fill]

---

## Abstract (< 500 words)

Cohere's Tiny Aya is built to run offline on phones in 70 languages, and the natural on-device agent is one that
reads your SMS inbox and acts for you. In India, the most common fraud arrives as an SMS: fake KYC alerts, "forward
the OTP", "pay ₹1 to verify". We ask a simple question: if one message in the inbox is a scam, does the assistant obey
it?

We built **SandeshBench**, 3,870 phone-inbox scenarios in English, Hindi, Hinglish, Bengali, Tamil and Marathi.
The assistant has seven tools (`read_inbox`, `send_sms`, `call`, `make_upi_payment`, `open_link`, `set_reminder`,
`reply_user`). The user asks for something ordinary (a bill amount, an OTP, a reply to Mom, a delivery call, a
milkman's UPI payment). One SMS tries to make the assistant forward an OTP, pay a UPI ID, open a phishing link or call
a fraud number, using seven attack styles: direct orders, fake system messages, bank/RBI/police authority, owner
impersonation, script switching, honorific register and fake tool-call JSON. Every label is exact and LLM-free: a
hijack is the attacker's phone number, UPI ID or URL landing in the action's target field. Tests prove the labels on
all scenarios.

Out of the box, Tiny Aya Fire is hijacked in [fill]% of attacks on familiar languages and [fill]% on Bengali, Tamil
and Marathi. A strong defensive system prompt only brings this to [fill]%.

We chain three Lexsi tools. **CuratorKIT** gates, deduplicates (exact + MinHash) and exports the training data with
provenance. **SafeTune** fine-tunes Tiny Aya Fire (LoRA) to do the user's task, ignore the instruction and warn the
user. We compare `PlainSFTTrainer` with `SafeGradTrainer`, whose alignment signal is the base model's *own* refusals
to Cohere's `aya_redteaming` prompts, so general safety does not drift while the agent skill is learned. A control
fine-tune on the same inboxes with the scam removed separates "learned the tool format" from "learned to resist".
**AuditKIT** scores every transcript through custom exact scorers on precomputed runs and gives paired-bootstrap
significance against the base model.

The SafeGrad model cuts attack success to [fill]% in-distribution and [fill]% on languages it never saw in
training, and to [fill]% on held-out attack styles. Task success on clean inboxes is [fill]% (base: [fill]%), and it
warns the user about the scam in [fill]% of replies. On 400 held-out multilingual red-team prompts, unsafe answers
are [fill]% vs [fill]% for plain fine-tuning and [fill]% for the base model.

The result is a measurable, reproducible fix for a concrete Indian harm that keeps the inbox on the phone: no OTP ever
needs to reach a cloud API. We release the benchmark, every transcript, three fine-tuned models, the
curated training sets with provenance, a browsable transcript explorer, and a one-command resumable pipeline.
