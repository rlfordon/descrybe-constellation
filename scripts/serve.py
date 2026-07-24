"""Run the descrybe-constellation web app locally.

    .venv/bin/python scripts/serve.py --port 8737

Binds 127.0.0.1 only -- single-user local tool, never exposed on the network.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import uvicorn

from constellation.web import load_env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8737)
    args = ap.parse_args()

    load_env()
    print(f"descrybe-constellation: http://127.0.0.1:{args.port}")
    uvicorn.run("constellation.web:app", host="127.0.0.1", port=args.port, app_dir=str(REPO))


if __name__ == "__main__":
    main()
