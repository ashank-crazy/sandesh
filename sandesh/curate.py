"""CuratorKIT stage: schema gate, exact + MinHash dedup, cleaning, export with provenance.

Each JSONL in ``data/sft`` becomes a CuratorKIT export folder in
``data/curated/<name>`` (``sft_messages`` config + manifest, dataset card,
checksums, lexsi_provenance.json). SafeTune trains straight from these folders.

    python -m sandesh.curate --data data
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def curate(src: Path, out: Path, name: str) -> dict:
    from curatorkit import Curator, CuratorConfig

    result = Curator(CuratorConfig(
        dataset=str(src),
        dedup="minhash",
        minhash_threshold=0.95,  # scenarios share a template; only drop true near-copies
        clean=True,
        # CuratorKIT's token gate measures the first exchange only (request +
        # read_inbox call), which is short by design; the real content is in later turns.
        min_tokens=1,
        max_tokens=8192,
        export_formats=["messages"],
        output_dir=str(out),
        name=f"sandesh_{name}",
    )).run()
    manifest = json.loads((out / "manifest.json").read_text())
    return {"name": name, "stage_counts": manifest.get("stage_counts"),
            "rejected": manifest.get("rejected_breakdown")}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--only", nargs="*", help="subset of: train train_clean dev safety")
    args = ap.parse_args(argv)
    data = Path(args.data)
    names = args.only or ["train", "train_clean", "dev", "safety"]
    report = []
    for name in names:
        src = data / "sft" / f"{name}.jsonl"
        if not src.exists():
            print(f"skip {name}: {src} not found")
            continue
        r = curate(src, data / "curated" / name, name)
        report.append(r)
        exported = (r["stage_counts"] or {}).get("MessagesExporter", {}).get("exported_count")
        print(f"curated {name}: exported={exported} rejected={r['rejected']}")
    (data / "curated").mkdir(parents=True, exist_ok=True)
    (data / "curated" / "curation_report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
