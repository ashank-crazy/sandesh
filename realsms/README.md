# Real scam SMS (final round, P6)

`scenarios.jsonl` holds 1,099 SandeshBench episodes. Each one ends with a real SMS as the newest message:
499 smishing messages and 600 legitimate ones. `build_report.json` gives the counts, the SHA-256 of both files and
the task mix. `python -m sandesh.realsms check` confirms the file is unchanged since it was committed, which was
before any model saw it. The pass rule is P6 in [FINAL_ROUND.md](../FINAL_ROUND.md).

## Source and licence

The SMS texts come from:

> Sandhya Mishra and Devpriya Soni, *SMS Phishing Dataset for Machine Learning and Pattern Recognition*,
> Mendeley Data, version 1, 2022. DOI [10.17632/f45bkkt8pr.1](https://data.mendeley.com/datasets/f45bkkt8pr/1).

The dataset is licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The authors credit Tiago A. Almeida's SMS Spam Collection and Dr. Gunikhan Sonowal for the messages.

### Changes we made

- Replaced unreadable bytes (U+FFFD) with a space and collapsed runs of whitespace.
- Removed exact duplicates. A text that appears under two labels was dropped from both.
- Kept the smishing messages that contain a phone number, short code, URL or email.
- Kept a fixed random sample of 600 legitimate messages, each 20 to 320 characters long.
- Placed each message in a generated English inbox, with a generated sender number and time.

We did not edit the message texts beyond these changes. Some texts are offensive or sexual, as real spam is.

Rebuild with:

```bash
python -m sandesh.realsms build --csv data/external/smishing/Dataset_5971.csv
```

This needs `Dataset_5971.csv` from the Mendeley page.
