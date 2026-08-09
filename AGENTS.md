# Repository Guidelines

## Structure

Solutions are grouped by language under `src/typescript/` and `src/python/`. Each problem uses
the zero-padded form `p_####_<slug>/`: TypeScript has `<stem>.ts` and `<stem>.test.ts`; Python
has `<stem>.py` and `test_<stem>.py`. Put reusable TypeScript data structures in
`src/typescript/data_structures/`; judge-provided TypeScript types are declared ambiently in
`src/typescript/judge-types.d.ts`. Repository workflow commands live in `scripts/`, and their
tests are in `tests/`.

## Tooling and commands

Install the pinned toolchain with `mise install`, JavaScript dependencies with `pnpm install`,
and Python dependencies with `uv sync --frozen`. `mise.toml` pins Node.js, pnpm, Python, and
uv. TypeScript uses Vitest and Biome; Python uses pytest and Ruff.

Create a solution pair with `pnpm new ts 1512 "Number of Good Pairs"` (or `py`). Pass the
optional canonical URL with `--url <url>` and the exact judge callable with
`--signature <signature>`. The scaffold creates files only; it performs no Git operations and
prints the suggested branch and focused test command.

- `pnpm test` runs all TypeScript and Python tests.
- `pnpm test:one <ts|py> <number>` resolves and runs one problem; TypeScript also accepts
  `--watch`.
- `pnpm test:ts <path>` and `pnpm test:py <path>` run focused tests; `pnpm test:ts:watch`
  starts Vitest watch mode.
- `pnpm submission <ts|py> <number>` prints judge-ready source; `--copy` copies it when a
  supported clipboard command is available.
- `pnpm run doctor` verifies the local toolchain, dependencies, and Git-hook installation.
- `pnpm lint`, `pnpm typecheck`, and `pnpm format:check` run individual read-only checks.
- `pnpm format` applies Biome and Ruff formatting.
- `pnpm check` runs format checks, linting, TypeScript type checking, and all tests; run it
  before submitting.
- `pnpm incomplete` reports untouched scaffold markers; `pnpm ready` requires none and then
  runs the complete checks.

## Style and tests

Use four spaces, UTF-8, final newlines, and no trailing whitespace. Keep explicit `.js`
extensions in relative TypeScript test/helper imports. TypeScript solution files should avoid
module imports, CommonJS module syntax, and triple-slash references so `pnpm submission` can
render them safely. Prefer named TypeScript exports, target ES2024 APIs, and include a concise
`time: O(...)` / `space: O(...)` comment in completed solutions. Python solutions normally use a
`Solution` class with LeetCode-compatible camelCase methods.

Co-locate tests with each solution. Cover supplied examples plus meaningful empty, singleton,
boundary, and duplicate cases. Test names follow Vitest's `*.test.ts` and pytest's `test_*.py`
conventions. Skip scaffold placeholders only until real examples are added.

## Commits and pull requests

Use focused, lowercase Conventional Commit subjects such as `feat: circular array loop` or
`feat(0283): move zeroes`. Branches generally use `feat/p-####-slug` or `chore/slug`. Pull
requests should summarize the algorithm and complexity, list validation commands run, and link
the LeetCode problem or relevant issue.
