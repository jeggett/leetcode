# Repository Guide

Optional personal working agreements: `~/.codex/AGENTS.md`, if present. This tracked guide
is self-contained; no external instruction file is required.

## Layout

Solutions are grouped by language under `src/typescript/` and `src/python/`. Each problem uses
`p_####_<slug>/`: TypeScript has `<stem>.ts` and `<stem>.test.ts`; Python has `<stem>.py` and
`test_<stem>.py`. Put reusable TypeScript data structures in `src/typescript/data_structures/` and
judge-provided types in `src/typescript/judge-types.d.ts`. Workflow commands live in `scripts/`,
with tests in `tests/`.

## Tooling and commands

Install the pinned toolchain with `mise install`, JavaScript dependencies with `pnpm install`, and
Python dependencies with `uv sync --frozen`. `.node-version` pins Node.js; `package.json` pins pnpm;
`mise.toml` pins Python and uv. Keep mise's idiomatic pnpm version-file support enabled. TypeScript
uses Vitest and Biome; Python uses pytest and Ruff.

Use `lc` as the public workflow command. `lc <leetcode-url>` fetches official metadata, creates
`feat/p-####-slug`, and scaffolds TypeScript; add `py` before the URL for Python. The file-only
fallback is `lc new [ts|py] <number> <title...>`, with optional `--url` and `--signature` metadata.

- `lc test` runs the current problem when detected from the caller directory or problem branch,
  otherwise all tests. Pass `[ts|py] <number-or-path>` explicitly; `lc watch` enables Vitest watch.
- `lc submit [ts|py] [number]` prints judge-ready source; `lc copy` also copies it.
- `lc doctor` checks the toolchain, dependencies, and Git-hook installation.
- `lc lint`, `lc typecheck`, and `lc format --check` run individual read-only checks; `lc format`
  applies Biome and Ruff formatting.
- `lc check` runs format checks, linting, TypeScript type checking, and all tests.
- `lc incomplete` reports untouched scaffold markers; `lc ready` requires none, then runs the full
  checks. Run `lc ready` before submitting.

The `pnpm` scripts remain stable low-level interfaces for automation and unusual runner options.

## Style and tests

Use four spaces, UTF-8, final newlines, and no trailing whitespace. Keep explicit `.js` extensions
in relative TypeScript test/helper imports. TypeScript solution files should avoid module imports,
CommonJS syntax, and triple-slash references so `lc submit` can render them safely. Prefer named
exports, target ES2024 APIs, and include a concise `time: O(...)` / `space: O(...)` comment in
completed solutions. Python solutions normally use a `Solution` class with LeetCode-compatible
camelCase methods.

Co-locate tests with each solution. Cover supplied examples plus meaningful empty, singleton,
boundary, and duplicate cases. Use Vitest `*.test.ts` and pytest `test_*.py` names; skip scaffold
placeholders only until real examples are added.

## Commits and pull requests

Use focused, lowercase Conventional Commit subjects such as `feat: circular array loop` or
`feat(0283): move zeroes`. Branches generally use `feat/p-####-slug` or `chore/slug`. Pull requests
should summarize the algorithm and complexity, list validation commands, and link the LeetCode
problem or relevant issue.
