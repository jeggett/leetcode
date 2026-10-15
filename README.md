# LeetCode solutions

TypeScript and Python solutions with colocated tests and a repository-local
`lc` command for scaffolding, testing, and preparing submissions.

## Setup

Keep the checkout in the Linux filesystem when using WSL. Install and activate
[mise](https://mise.jdx.dev/getting-started.html), then run:

```sh
mise trust
mise install
pnpm install --frozen-lockfile
uv sync --frozen
pnpm prepare
lc doctor
```

The version files, `mise.toml`, and `package.json` declare the toolchain.
`pnpm-lock.yaml` and `uv.lock` lock dependencies. Mise adds `bin/` to `PATH`;
`bin/lc` also works directly. `bin/setup --trust` automates installation.

TypeScript uses Vitest, Biome, and the ES2024 target. Python uses pytest and
Ruff. The pre-commit hook and GitHub Actions run the complete `ready` gate.

For VS Code, accept the workspace extension recommendations and select
`.venv` as the Python interpreter. Workspace tasks cover scaffolding, tests,
watch mode, formatting, and validation.

Doctor only checks setup prerequisites. Use `mise current` to inspect tool
versions, the frozen install commands to synchronize dependencies, and
`pnpm prepare` to reinstall hooks. `lc ready` validates the actual workspace.

## Daily workflow

```sh
lc https://leetcode.com/problems/search-insert-position/
# Implement the solution and replace the skipped scaffold tests.
lc test 35
lc ready
lc copy 35
```

URL scaffolding fetches the official signature and writes the solution and
test files. It refuses existing problem IDs. Use `lc py URL` for Python.
Scaffolding never changes Git branches or requires a clean worktree; use
ordinary Git commands when you want a separate problem branch.

For offline work, design-class problems, or unsupported judge types:

```sh
lc new py 1512 Number of Good Pairs
lc new ts 1512 Number of Good Pairs \
  --signature 'numIdenticalPairs(nums: number[]): number'
```

Manual scaffolding only writes files. It accepts `--url URL` and
`--signature SIGNATURE`. Replace all generated markers before `lc ready`.

## Commands

`LANG` accepts `ts`/`typescript` or `py`/`python`.

| Command | Action |
| --- | --- |
| `lc test [LANG] [ID\|PATH]` | Run the selected or current problem |
| `lc test all` | Run both complete test suites |
| `lc test LANG` | Run one language's complete suite |
| `lc watch [ID\|PATH]` | Watch TypeScript tests |
| `lc submit [LANG] [ID]` | Check and print judge-ready source |
| `lc copy [LANG] [ID]` | Check, print, and copy the submission |
| `lc incomplete` | Find generated scaffold markers |
| `lc ready` | Require complete scaffolds and run all checks |
| `lc check` | Run formatting checks, lint, types, and tests |
| `lc format [LANG]` | Apply formatting |
| `lc format [LANG] --check` | Check formatting without edits |
| `lc lint [LANG]` | Run linters |
| `lc typecheck` | Check TypeScript types |
| `lc doctor` | Find missing tools and local dependency files |

Tests accept a solution or test file path, relative to the calling directory.
Use `--` to pass runner options: `lc test py 1512 -- -q` or
`lc test 268 -- -t missing`. `lc test --watch` is equivalent to `lc watch`.

Without an explicit target, `lc` detects the current problem from the caller's
problem directory, then a matching `feat/p-####-slug` branch. If no problem is
detected, `lc test` runs all tests and `lc submit` requires an ID. Explicit IDs
default to TypeScript; paths infer their language.

Submission checks require complete source and tests and a passing focused
suite. `--no-check` skips that preflight. `--copy` also copies the output;
`--copy-only` copies it and prints a confirmation instead of source. The
TypeScript renderer removes supported exports and rejects module dependencies.
Python source is emitted unchanged.

Aliases: `t=test`, `w=watch`, `s=submission=submit`, `r=ready`, `c=check`,
`f=fmt=format`, `fc=format-check`, `n=add=a=new`, `d=doctor`,
`types=typecheck`, and `test-all=test all`. `lc help` shows a short reference.
Existing pnpm scripts remain available for automation.

## Layout and conventions

Each problem lives in `src/LANGUAGE/p_####_<slug>/`. TypeScript uses
`<stem>.ts` and `<stem>.test.ts`; Python uses `<stem>.py` and `test_<stem>.py`.
Workflow implementation is in `scripts/`, with tests in `tests/`.

Keep solutions compatible with the judge's signature and input constraints.
Use named TypeScript exports and explicit `.js` extensions in test imports.
Judge types live in `src/typescript/judge-types.d.ts`; reusable test helpers
live in `src/typescript/data_structures/`.

Test supplied examples and meaningful boundaries, including mutation behavior.
Add failed judge inputs as regression tests. Document time and auxiliary-space
complexity, run `lc ready`, and commit the focused change. See
[CLAUDE.md](CLAUDE.md) for repository maintenance guidance.

## License

[MIT](LICENSE).
