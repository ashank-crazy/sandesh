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


def build_mix(data: Path) -> Path:
    """Ablation set: the Sandesh SFT data plus the same self-distilled refusals SafeGrad uses as its
    anchor, simply mixed in. Answers "is SafeGrad better than just adding refusal data?"."""
    dst = data / "sft" / "train_mix.jsonl"
    rows = []
    for name, source in (("train", "sandesh"), ("safety", "safety_anchor")):
        for line in (data / "sft" / f"{name}.jsonl").open(encoding="utf-8"):
            r = json.loads(line)
            rows.append({"id": r["id"], "lang": r["lang"], "source": source, "messages": r["messages"]})
    with dst.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return dst


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--only", nargs="*", help="subset of: train train_clean dev safety train_mix")
    args = ap.parse_args(argv)
    data = Path(args.data)
    names = args.only or ["train", "train_clean", "dev", "safety"]
    rep_path = data / "curated" / "curation_report.json"
    report = {r["name"]: r for r in json.loads(rep_path.read_text())} if rep_path.exists() else {}
    for name in names:
        if name == "train_mix":
            build_mix(data)
        src = data / "sft" / f"{name}.jsonl"
        if not src.exists():
            print(f"skip {name}: {src} not found")
            continue
        r = curate(src, data / "curated" / name, name)
        report[name] = r
        exported = (r["stage_counts"] or {}).get("MessagesExporter", {}).get("exported_count")
        print(f"curated {name}: exported={exported} rejected={r['rejected']}")
    (data / "curated").mkdir(parents=True, exist_ok=True)
    rep_path.write_text(json.dumps(list(report.values()), indent=2))


if __name__ == "__main__":
    main()
