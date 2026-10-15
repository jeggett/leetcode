#!/usr/bin/env bash

# Run the scaffold from the repository root with the pinned toolchain.
cd -- "$(dirname -- "$0")"
exec mise exec -- uv run python -m scripts.new_problem "$@"
