"""Prepare a content-only Docker seed without exposing the live DB to Docker."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from tools.create_seed_database import create_seed
except ModuleNotFoundError:  # Direct execution: python tools/prepare_docker_seed.py
    from create_seed_database import create_seed


def prepare(source: Path, destination: Path) -> Path:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("Seed destination must differ from the live database")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    create_seed(source, temporary)
    os.replace(temporary, destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("speakseed.db"))
    parser.add_argument("--destination", type=Path, default=Path(".docker-build/seed.db"))
    args = parser.parse_args()
    prepared = prepare(args.source, args.destination)
    print(str(prepared).encode("ascii", "backslashreplace").decode("ascii"))
