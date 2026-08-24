# LeetCode solutions

A local TypeScript and Python workspace for solving LeetCode problems, practicing interview
patterns, and validating a solution before it is submitted. Problems keep their implementation,
tests, metadata, and notes together; the `lc` command ties the workflow together.

## Start here

Install the pinned toolchain and frozen dependencies from the repository root:

```bash
./bin/setup --trust
```

`--trust` explicitly trusts this repository's `mise.toml`. After the first run, `./bin/setup` is
safe to repeat. The setup script installs the pinned tools, runs `pnpm install --frozen-lockfile`,
syncs the frozen Python environment, and installs the Husky hook.

The repository-local `lc` is added to `PATH` by `mise`. If another system command owns the name
`lc`, use the unambiguous wrapper instead:

```bash
./bin/leetcode --help
./bin/leetcode today
```

Verify the checkout before solving:

```bash
lc doctor
lc compat
```

## Pinned runtime and judge profile

The source of truth is `lc.toml` plus the version files and lockfiles. The supported profile is:

| Tool/profile | Version | Role |
| --- | --- | --- |
| Node.js | 26.7.0 (Current) | TypeScript runtime and tooling |
| TypeScript | 5.7.3 | Compiler and judge-facing language profile |
| Python | 3.14.x (local pin 3.14.7) | Python solutions and scripts |
| pnpm | 11.20.0 | JavaScript package manager |
| uv | 0.12.2 | Python environment and dependencies |
| TypeScript target | ES2024 | Judge-compatible compiler target |

`mise.toml` provides the tools and adds `bin/` to `PATH`; `.node-version` and `.python-version`
make the runtime pins visible to other tooling. Keep the checkout on the WSL/Linux filesystem
(for example `~/prj/leetcode`), rather than under `/mnt/c`, for faster Git, dependency, and watch
operations.

## Daily loop

Choose work, start it, iterate quickly, then record the result:

```bash
lc today                         # due work first, then unseen work
lc start 1512                    # resume/create a local problem and start its timer
lc test                          # focused tests from a problem directory or branch
lc watch                         # watch the current TypeScript/Python tests
lc ready                         # current problem, or changed scope when none is detected
lc submit py 1512                # focused check, then print judge-ready source
lc finish --result solved --confidence 4
```

For a new LeetCode problem, pass its URL to `start`:

```bash
lc start https://leetcode.com/problems/search-insert-position/
lc start py https://leetcode.com/problems/search-insert-position/
```

`start` is idempotent. It resumes an existing problem branch, otherwise creates the conventional
`feat/p-####-slug` branch from configured `repository.base_branch` (normally `main`) and scaffolds
the problem. Use `--from-current` when branching deliberately from the current branch,
`--no-branch` to scaffold on the current branch, and `--no-timer` when no practice session should
be started. `lc resume [ID]` only switches to an existing problem branch. `lc current` reports the
detected problem, branch, source path, and test path.

`lc begin [ts|py] [ID]` starts a practice timer without changing Git branches. If no ID is given,
it selects the first due or unseen problem. A repeated `lc start` for the active problem continues
its timer rather than creating a second session.

## Command reference

### Create and select problems

| Command | Purpose |
| --- | --- |
| `lc start [ts|py] URL\|ID` | Create/resume a problem branch and, by default, start its timer |
| `lc resume [ts|py] [ID]` | Switch to an existing problem branch |
| `lc current` | Show detected problem, branch, source, and test paths |
| `lc URL` / `lc py URL` | Legacy URL scaffold spelling; preserved for compatibility |
| `lc new [ts|py] ID TITLE...` | Offline/manual scaffold with optional metadata flags |

Manual scaffolds accept `--url`, `--signature`, `--difficulty`, `--topic`, `--kind`,
`--example`, and `--target-minutes`. URL scaffolding fetches LeetCode metadata, including the
official starter for class/design-shaped problems when a simple function signature is not enough.

### Test, watch, submit

| Command | Purpose |
| --- | --- |
| `lc test` | Test the detected problem |
| `lc test [ts\|py] ID` | Run one problem's colocated test |
| `lc test [ts\|py] PATH` | Test a file; a solution path resolves to its colocated test |
| `lc test [ts\|py] all` | Run one language's complete suite |
| `lc test all` | Run all TypeScript and Python tests explicitly |
| `lc watch [ts\|py] [ID\|PATH]` | Watch focused TypeScript or Python tests |
| `lc watch [ts\|py] all` | Watch a complete language suite |
| `lc submit [ts\|py] [ID]` | Check the focused problem, then print judge-ready source |
| `lc copy [ts\|py] [ID]` | Check and copy the submission without printing it |

Outside a detected problem context, bare `lc test` and `lc watch` stop with guidance; use an
explicit `all`. Use `lc COMMAND --help` for runner-specific options and focused path forms.

Submission commands reject incomplete scaffolds and run the focused test by default. Use
`lc submit ... --no-check` only when the safety check is intentionally handled elsewhere;
`lc submit ... --copy` prints the source and copies it, while `lc copy ...` is copy-only.

### Practice and review

Practice state is local, append-only history in the ignored `.lc/` directory. It does not modify
accepted solutions or branches.

| Command | Purpose |
| --- | --- |
| `lc today [ts\|py] [--limit N]` | Select due problems before unseen problems |
| `lc begin [ts\|py] [ID] [--mode new\|review\|mock]` | Start a timed session |
| `lc finish --result solved\|hinted\|failed [--confidence 1-4]` | Finish and schedule review |
| `lc review [ts\|py] [ID]` | Show due work or start a review session |
| `lc retry [ts\|py] ID` | Create a blank isolated retry artifact |
| `lc list [ts\|py] --due\|--unseen` | Show practice status |
| `lc stats [ts\|py]` | Show attempts, completion, timing, and weak patterns |

`lc finish` also accepts `--elapsed SECONDS` to override the measured timer and `--notes TEXT`.
A solved session's review interval grows with confidence; hinted and failed sessions return
sooner. Retry files live under `.lc/practice-attempts` and never contain the accepted solution
body. The retry builder preserves the callable interfaces required by the copied test and stops
with guidance when an imported shape cannot be recreated safely.

### Quality and diagnostics

| Command | Purpose |
| --- | --- |
| `lc ready` | Run the current-problem gate, or changed-scope gate when no context is detected |
| `lc ready --current` | Gate the detected problem only |
| `lc ready --changed` | Gate changed problems (falling back to a full gate for tooling changes) |
| `lc ready all` | Run the complete repository gate explicitly |
| `lc check` | Format checks, lint, typecheck, and all tests |
| `lc format [ts\|py] [--check]` | Apply or check formatting |
| `lc lint [ts\|py]` | Run both or one language's linter |
| `lc typecheck` | Type-check TypeScript |
| `lc incomplete` | Find untouched scaffold markers |
| `lc doctor` | Check pinned tools, dependencies, hooks, WSL, and clipboard support |
| `lc compat` | Check the configured judge profile against project metadata |

`lc format` can modify files; the other quality commands are intended to be read-only. The
pre-commit hook uses the staged changed-scope gate. Use `lc COMMAND --help` for command-specific
usage. Short aliases include `t`, `w`, `s`, `r`, `c`, `fmt`, `fc`, `d`, and `types`.

## Problem layout and metadata

Each problem directory uses a zero-padded ID and keeps source beside its test:

```text
src/
├── typescript/p_1512_number_of_good_pairs/
│   ├── p_1512_number_of_good_pairs.ts
│   ├── p_1512_number_of_good_pairs.test.ts
│   ├── problem.toml
│   └── notes.md
└── python/p_1512_number_of_good_pairs/
    ├── p_1512_number_of_good_pairs.py
    ├── test_p_1512_number_of_good_pairs.py
    ├── problem.toml
    └── notes.md
```

`problem.toml` stores queryable identity and study metadata such as language, kind, difficulty,
topics, target minutes, signature, and URL. `notes.md` is a short retrieval prompt for examples,
invariants, complexity, and mistakes. `tracks/interview-core.toml` supplies optional pattern and
difficulty defaults; problem-local metadata wins. The TypeScript helper directory and
`judge-types.d.ts` contain shared judge-facing support, while Python solutions remain dependency
free unless the problem itself requires otherwise.

## VS Code

Open the repository through VS Code's WSL support and accept the workspace recommendations. Use
`${workspaceFolder}/.venv` as the Python interpreter. Included tasks cover ready, formatting,
current-problem tests, current-file tests, watch mode, and scaffolding. Launch configurations cover
the current Vitest and pytest problem. Running from the problem directory preserves `lc`'s context
detection.

## Troubleshooting

- Run `lc doctor` first. It reports missing runtimes, dependency metadata, Husky installation,
  WSL placement, and clipboard support without attempting repairs.
- If setup has not completed or `mise.toml` is untrusted, run `./bin/setup --trust` and retry.
- If `lc` resolves to an unrelated system command, use `./bin/leetcode ...`; it always invokes
  this checkout's wrapper.
- If a bare `lc test` or `lc watch` refuses to run, move into the problem directory or use an
  explicit ID/path. Use `lc test all` or `lc watch ts all` for a suite.
- Starting a problem requires a clean worktree before switching branches. Use `--from-current` or
  `--no-branch` only when that branch choice is deliberate.
- If `lc ready` reports incomplete markers, replace the generated TODO/skip placeholders before
  committing. Use `lc ready all` for the final repository-wide check.
- If clipboard support is missing, install one of the commands reported by `lc doctor` (`wl-copy`,
  `xclip`, `xsel`, or `clip.exe`) and retry `lc copy`.
- If Git hooks are missing, run `mise exec -- pnpm prepare` (or rerun setup), then confirm with
  `lc doctor`.

## Contributing and verification

Add a focused test with every solution change. Typical checks after setup are:

```bash
mise exec -- uv run pytest
mise exec -- pnpm exec vitest run
mise exec -- pnpm ready:all
git diff --check
```

For a narrower iteration, use `mise exec -- uv run pytest tests/test_lc.py` or
`mise exec -- pnpm exec vitest run src/typescript/p_1512_number_of_good_pairs`. Keep generated
metadata and notes with the problem, avoid committing `.lc/`, and inspect `git diff` before
committing. Branches conventionally use `feat/p-####-slug` and commit messages should identify the
problem and approach.

## License

This repository is licensed under the terms in [LICENSE](LICENSE).
