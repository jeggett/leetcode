# Repository Guide

Optional personal agreements: `~/.codex/AGENTS.md`, if present. This guide
is self-contained; no external instruction file is required.

## Layout

Solutions live in `src/typescript/` and `src/python/`, grouped by
`p_####_<slug>/`. TypeScript uses `<stem>.ts` and `<stem>.test.ts`; Python
uses `<stem>.py` and `test_<stem>.py`. Shared TypeScript test helpers belong
in `src/typescript/data_structures/`, and Python helpers in
`src/python/data_structures/`; judge types belong in
`src/typescript/judge-types.d.ts`. Node conversion helpers are for tests.

Workflow commands live in `scripts/`, with tests in `tests/`. Run Python
commands as modules from the repository root: `python -m scripts.NAME`.
`arguments.py` defines shared command options, `problem_paths.py` resolves
source and test paths, and `typescript.mjs` uses Babel for signatures and
submission rendering. Reuse these boundaries when adding behavior.

## Tooling and commands

Install tools with `mise install`, JavaScript dependencies with
`pnpm install --frozen-lockfile`, and Python dependencies with
`uv sync --frozen`. Keep tool declarations in `mise.toml`, version files,
and `package.json` consistent. `.node-version` is the authoritative Node.js
pin; `mise.toml` enables version files and pins pnpm, Python, and uv.
Install the additional judge runtime with
`mise install "node@$(cat .judge-node-version)"`; `bin/setup` includes this.
`pnpm prepare` installs the Git hook.

Use `lc` for interactive work:

- `lc URL` fetches metadata and scaffolds TypeScript. Use `lc py URL`
  for Python. Clear JSON examples become tests; uncertain judging rules
  keep an editable skipped template. Scaffolding never changes Git state.
- `lc new [ts|py] ID TITLE...` scaffolds files without Git or network access.
  It accepts optional `--url` and `--signature` metadata.
- `lc test` runs the detected problem or, without context, all tests.
  Pass `[ts|py] ID|PATH` explicitly; source paths resolve to their tests.
  Runner options follow `--`. `lc watch` watches TypeScript tests.
- `lc submit [ts|py] [ID]` checks and renders a submission. `lc copy`
  also copies it. `--copy-only` suppresses source output; `--no-check`
  explicitly skips the focused preflight.
- `lc doctor` checks command and local dependency presence. Use mise and
  frozen installs for versions; `pnpm prepare` installs hooks.
- `lc lint`, `lc typecheck`, and `lc format --check` run individual checks.
  `lc format` applies formatting.
- `lc check` runs formatting checks, lint, TypeScript types, all tests,
  and `pnpm judge:check`. The judge gate typechecks rendered submissions
  with TypeScript 5.7.3 and runs TypeScript tests with Node.js 22.14.0.
- `lc ready` rejects incomplete scaffolds before running `lc check`.
  Run it before submitting or committing.

The pnpm scripts remain stable low-level interfaces for automation. Git
commit, push, and pull remain ordinary Git commands. See README.md for setup
and the full command reference.

## Style and tests

Use four spaces, UTF-8, final newlines, and no trailing whitespace.
TypeScript targets ES2024. Keep explicit `.js` extensions in relative test
and helper imports. Solutions should use named exports and avoid imports,
CommonJS syntax, and triple-slash references so rendering stays safe.
Python normally uses a `Solution` class with judge-compatible camelCase
methods and built-in collection annotations such as `list[int]`.

Completed solutions include `time: O(...)` / `space: O(...)` comments.
Colocate tests and cover supplied examples plus meaningful boundaries,
duplicates, and mutation behavior. Replace skipped scaffold tests before
running `lc ready`. Keep regression tests for failed judge inputs.

## Commits and pull requests

Use short Conventional Commit subjects and PR titles, with an issue ID
when available. PR descriptions contain only `Closes ISSUE-ID`, or remain
empty without an issue. Report validation in chat.
