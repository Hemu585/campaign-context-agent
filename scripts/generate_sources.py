"""Render the fictional source documents for a dataset from its dataset.json.

    .venv/Scripts/python.exe scripts/generate_sources.py            # write files
    .venv/Scripts/python.exe scripts/generate_sources.py --check    # fail on drift

The seed stores each document's exact text and SHA-256 checksum in FalkorDB.
"""

from __future__ import annotations

import argparse
import sys

from app.db.dataset import DATA_ROOT, load_dataset, source_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="demo_v1")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    root = DATA_ROOT / args.dataset
    ds = load_dataset(args.dataset, check_files=False)
    (root / "sources").mkdir(parents=True, exist_ok=True)
    drift = []
    for seed in ds.sources:
        path = source_file(root, seed)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != seed.text:
            drift.append(path.name)
            if not args.check:
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(seed.text)
    expected = {source_file(root, s).name for s in ds.sources}
    extra = sorted(p.name for p in (root / "sources").glob("*.md") if p.name not in expected)
    if args.check:
        if drift or extra:
            print(f"drift: {drift} extra: {extra}")
            return 1
        print(f"ok: {len(ds.sources)} source documents match {args.dataset}")
        return 0
    print(f"wrote {len(drift)} of {len(ds.sources)} source documents; unexpected files: {extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
