## Cost per request and per month (1,000,000 users × 10 requests/day)

Measured on `safegrad_sandesh` over 1330 test requests on NVIDIA GeForce RTX 3090: 932 prompt tokens and 59 output tokens per request on average, 2,641 requests per GPU-hour.

| Deployment | $ / request | $ / month | Privacy |
|---|---|---|---|
| closed small API model (token billing) | 0.000175 | 52,493 | inbox (incl. OTPs) leaves the phone |
| Self-hosted Tiny Aya Fire on A100 40GB (GPU-hours, HF generate, no batching server) | 0.000682 | 204,455 | inbox leaves the phone, goes to your server |
| On-device Tiny Aya Fire (Q4, ~2 GB) | 0.000000 | 0 | inbox never leaves the phone |

Prices used (inputs, verify before quoting): API $0.15/1M in, $0.6/1M out; GPU $1.8/hour. On-device marginal cost is zero; the user's phone pays in battery.
