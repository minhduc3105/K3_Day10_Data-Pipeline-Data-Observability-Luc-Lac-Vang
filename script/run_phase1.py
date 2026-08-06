from __future__ import annotations

import argparse

from pipelines.phase1 import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the baseline Crossref RAG pipeline.")
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--refresh-testset", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    args = parser.parse_args()
    main(**vars(args))
