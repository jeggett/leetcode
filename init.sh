#!/usr/bin/env bash

cd -- "$(dirname -- "$0")"
exec mise exec -- uv run python scripts/new_problem.py "$@"
