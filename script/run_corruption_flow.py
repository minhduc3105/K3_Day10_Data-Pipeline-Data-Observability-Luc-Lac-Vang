from __future__ import annotations

import argparse

from pipelines.corruption_flow import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the corruption and repair experiment.")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    args = parser.parse_args()
    main(**vars(args))
