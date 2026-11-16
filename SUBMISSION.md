# Submission form answers (round 1)

The form is https://hackathon.lexsi.ai/submission/ (a Tally form, four pages). Fill it in this order. Numbers are from
the round-1 run (`results/summary.md`, Nov 16 2026). You can submit more than once; the latest submission counts.

## Page 1: Your team

- **Registered email:** the email you registered with.
- **Abstract:** paste everything inside the box below (plain text, 490 words; the form limit is 500).
- **Discord username:** yours (optional).

```text
Cohere's Tiny Aya runs offline on phones, and the natural on-device agent reads your SMS inbox and acts for you. In India, the most common fraud arrives as an SMS. If one message in the inbox is a scam, does the assistant obey it?

SandeshBench has 3,870 phone-inbox scenarios in English, Hindi, Hinglish, Bengali, Tamil and Marathi: seven tools, seven everyday user tasks, and one SMS that tries to make the assistant forward an OTP, pay a UPI ID, open a phishing link or call a fraud number, in seven attack styles. Labels are exact and LLM-free: a hijack is the attacker's number, UPI ID or URL in the action's target field. Bengali, Tamil, Marathi and two attack styles are held out of training.

Out of the box, Tiny Aya Fire obeys 14.0% of scam SMS (16.0% in held-out languages, 27.0% when the scam switches script mid-message). Given 16 rewrites per scam (encodings, character noise, spoofed senders, urgency), the attacker wins 52.1% of scenarios. A defensive system prompt lowers attack success to 4.3%, but clean-inbox task success falls from 48.3% to 38.8%.

We chain three Lexsi Track 2 repos. CuratorKIT gates, deduplicates and exports the training data with provenance. SafeTune fine-tunes Tiny Aya Fire (LoRA) to do the user's task, ignore the instruction and warn the user. We compare PlainSFTTrainer, SafeGradTrainer anchored to the base model's own refusals of aya_redteaming prompts, and a control trained on the same inboxes with the scam removed. AuditKIT scores every transcript with exact scorers and paired-bootstrap significance, and audits multi-turn episodes with agent_eval.

Plain SFT brings attack success to 0.0% on all four test splits, unseen languages and attack styles included, and to 0.0% under best-of-16 (95% CI 0-7.4%). Clean-inbox task success rises from 48.3% to 99.5%, and it warns the user in 94.9% of attacked replies. The weak spot is delegation: when the scammer follows up and the user says "take care of whatever is urgent", 20.0% of three-turn episodes are hijacked (base 67.5%). General behavior holds: unsafe answers on 400 held-out multilingual red-team prompts 4.0% (base 5.5%), XSTest over-refusal 12.4% (base 11.6%), Global-MMLU en/hi/bn 49.0% (base 48.0%).

Two findings we did not expect. First, the scam-free control already cuts attack success to 1.2%: much of the base model's vulnerability comes from not knowing the task, not from a drive to obey. But the control never warns the user and still falls for script-switched and fake tool-call scams; only training on attacks closes the gap. Second, SafeGrad was not needed: plain SFT did not erode general safety, so the anchor had nothing to protect. SafeGrad kept harmful-prompt behavior at the base level (5.8% unsafe) but cost task success (95.7%) and warnings (78.9%), and let 2.1% of best-of-16 attacks through.

We release the benchmark, every transcript, the models, the curated data, an explorer and a one-command pipeline. The fix keeps the inbox on the phone: no OTP ever needs to reach a cloud API.
```

## Page 2: Your artifacts

- **Hugging Face model collection:** https://huggingface.co/collections/ashank-crazy/sandesh-models
- **Hugging Face dataset collection:** https://huggingface.co/collections/ashank-crazy/sandesh-datasets
- **Hugging Face article:** https://github.com/ashank-crazy/sandesh#readme (the form allows a GitHub README)
- **GitHub repo:** https://github.com/ashank-crazy/sandesh

Also public (not asked by the form; linked from the README): the transcript explorer
https://huggingface.co/spaces/ashank-crazy/sandesh-explorer

## Page 3: Repos, models, tracks

- **Which repos did you use?** CuratorKIT, SafeTune, AuditKIT. (Not CircuitKIT: its discovery did not finish for
  round 1.)
- **Which models did you use?** Tiny Aya Fire, Other.
- **Which other models?** Qwen3Guard-Gen-4B (safety judge)
- **Which track?** Track 2a: AI Safety and Red Teaming, and Track 2b: AI Safety and Correction.
- **Track 2a problem statements (at most 2):** Adversarial and safety evaluation sets; Multilingual and code-mixed
  safety.
- **Track 2b problem statements (at most 2):** Safety-preserving fine-tuning.

## Page 4: Consent and checklist

- The two consent boxes (partner promotion, being tagged) are optional; ticking them helps visibility.
- **Required:** "All repos and collections are public and final as of Nov 15, 11:59 PM AoE. Nothing changes after the
  deadline." True now. After 17:29 IST Nov 16, do not run `sandesh.publish` again and do not change these HF repos or
  collections; final-round work goes to new repos and a separate git branch (the `round1` tag marks this state).
- Solve the captcha, then submit.

## Project facts (for reference)

- **Project:** Sandesh (संदेश): stopping scam-SMS prompt injection in an on-device multilingual assistant
- **Core model:** `CohereLabs/tiny-aya-fire`. Supplementary: `Qwen/Qwen3Guard-Gen-4B` (judge),
  `HuggingFaceTB/SmolLM2-135M-Instruct` (CPU smoke tests only).
- **Datasets used:** `CohereLabs/aya_redteaming` (anchor, harmful-prompt eval), `Paul/XSTest` (over-refusal),
  `CohereLabs/Global-MMLU` (capability), SandeshBench (ours).
- **Models released:** `ashank-crazy/tiny-aya-fire-sandesh-sft` (plain SFT, recommended),
  `ashank-crazy/tiny-aya-fire-sandesh-safegrad`, `ashank-crazy/tiny-aya-fire-sandesh-sft-clean` (control).
