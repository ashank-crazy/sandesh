# Feedback for Lexsi: what we hit using the stack

Sandesh used every kit in the chain on Tiny Aya Fire (Cohere2, 36 layers × 16 heads, 262,144-token vocabulary) on one
shared RTX 3090 (24 GB): CuratorKIT for near-duplicate filtering, SafeTune for training (PlainSFT, plus SafeGrad as
a comparison), AuditKIT for paired bootstrap tests and `agent_eval`, and CircuitKIT 0.2.3 for EAP-IG. Everything
below comes from real runs; the file and function names point at the workaround in this repo.

## What worked well

- **AuditKIT's paired bootstrap** made every "better than base" claim checkable with one call, including the
  4-bit regression (base attack success 14.0% → 16.2%, p = 0.007) that we would otherwise have dismissed as noise.
- **`lexsi_provenance.json`** follows each dataset and checkpoint through the chain, so the published model card
  can name exactly which curated set trained it.
- **`agent_eval`** gave an independent safety check on all 120 multi-turn conversations (v2.1: 120/120 verified safe).

## 1. CircuitKIT: memory on long prompts (the one that cost us most)

Our inboxes are 845–1,400 tokens. With the defaults, three allocations ran the 24 GB card out of memory:

| What | Size | Our workaround (`sandesh/circuit.py`) |
|---|---|---|
| TransformerLens builds a `[pos × heads × d_head × d_model]` temporary for per-head outputs | 6.6 GiB at 845 tokens | set `CIRCUITKIT_TL_MEMORY_PATCH=1` before importing CircuitKIT |
| Unembedding every position (`[batch × seq × 262,144]` logits and their gradient) for every integrated-gradients step | 7.3 GiB at ~1,400 tokens | `_last_position_unembed`: the metric reads one token |
| `torch.where(isnan(pattern), …)` after the softmax keeps a mask and a second pattern copy per layer | 2 × `[heads × pos × pos]` per layer | `_WhereIfNeeded`: returns the pattern unchanged when nothing is NaN |

Even with all three, only the 32 shortest of our 88 dev pairs fit beside other jobs.

**Suggestions.** Turn the memory patch on by default for node attribution, or say in the README when it is needed.
It is off because it changes bf16 rounding; that trade-off is worth stating next to the flag. Unembed only the
positions the metric reads. Add a short table of memory against sequence length so users can size runs up front.

## 2. CircuitKIT: `attribute_node` asks for a flag node scores never read

`attribute_node(method="EAP-IG-inputs")` checks for `use_split_qkv_input`. Only edge attribution reads those
per-head input copies (3 × `[pos × heads × d_model]` per layer, kept for backward). We call
`get_scores_eap_ig` directly with the flag off (`_lean_for_attribution`). **Suggestion:** require the flag only for
edge attribution.

## 3. CircuitKIT: dependency pins

CircuitKIT 0.2.3 pins `huggingface-hub<2` and `transformer-lens` 3.8, which conflict with current `transformers`
in the same environment. We run it from a second virtualenv (`requirements-ck.txt`, `.venv-ck`). **Suggestion:**
relax the hub pin, or ship the TransformerLens dependency as an extra.

## 4. SafeTune: SafeGrad cost

- **Step time.** SafeGrad took 9.46 s/step against about 6 s/step for PlainSFT on the same data and card (~1.6×).
  It runs a second forward and backward pass on the safety batch, then projects the gradients.
- **Memory.** The KL reference loads as a second full copy of the base model (+6.7 GB for Tiny Aya). With a LoRA
  policy, the same logits come from the policy with its adapters switched off. We do that in `train.py`
  (`_BaseView`, with `--reference-copy` to restore the default).
- **Suggestion:** offer the adapters-off reference as a built-in option whenever the policy is LoRA.
- **Data point.** On this task SafeGrad did not beat PlainSFT:

  | | SafeGrad | PlainSFT |
  |---|---|---|
  | Attack success | 0.4% | 0.0% |
  | Task success on a clean inbox | 95.7% | 99.5% |
  | Hijacked by turn 3 (multi-turn) | 24.2% | 20.0% |

  That is a result, not a bug; SafeGrad may need tuning for agentic tool calls.

## 5. CuratorKIT: near-duplicate filtering vs deliberate contrastive pairs

v2.1 trains on matched pairs: the same inbox with and without a credit-card bill, differing in one SMS. Their
character-3-gram Jaccard reaches 0.92. That is under the 0.95 default, but close enough that a slightly
different template would have had CuratorKIT drop one half of a pair and quietly break the contrast. We raised the
threshold to 0.97 for this one set (`sandesh/curate.py`, `THRESHOLD`); 2 of 1,260 rows were dropped. Hashing
without the system prompt was the right default. **Suggestion:** a "group id" field whose members are never
deduplicated against each other, so intended near-duplicates survive at the normal threshold.

## 6. Multi-turn data: chat templates that require alternating roles

Tiny Aya's chat template, like many, rejects a conversation whose roles do not alternate. In an agent episode a
tool result (sent as a user message) is often followed by the user's next request, which makes two user messages in
a row. We merge consecutive same-role messages (`multiturn._alternate`) and use the same function for training rows
and for the audit, so the two cannot drift apart. **Suggestion:** have SafeTune and `agent_eval` either normalise
roles or fail with a message that names the template. Otherwise each user writes their own merge, and training and
evaluation formats can quietly diverge.

## 7. Small: local import on macOS

On macOS with Python 3.12.0, importing CuratorKIT (through `datasets` → `multiprocess`) ends with
`AttributeError: '_thread.RLock' object has no attribute '_recursion_count'` from `multiprocess`'s resource
tracker. It is an upstream `multiprocess` / Python 3.12.0 issue rather than CuratorKIT's own code; a
minimum Python version or a note in the install section would save the next person some time.
