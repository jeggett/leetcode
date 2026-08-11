# LeetCode solutions

A local TypeScript and Python workspace for solving LeetCode problems, reproducing failed
submissions, and validating examples and edge cases before submitting again.

Each problem keeps its implementation next to its tests. The repository pins its complete
toolchain, provides a safe scaffold for new problems, and exposes the complete day-to-day
workflow through one `lc` command.

## Repository layout

```text
src/
├── python/
│   └── p_####_<slug>/
│       ├── p_####_<slug>.py
│       └── test_p_####_<slug>.py
└── typescript/
    ├── data_structures/
    ├── judge-types.d.ts
    └── p_####_<slug>/
        ├── p_####_<slug>.ts
        └── p_####_<slug>.test.ts
bin/
└── lc
scripts/
├── check_incomplete.py
├── doctor.py
├── lc.py
├── new_problem.py
├── problem_paths.py
├── submission.py
└── test_one.py
tests/
└── test_*.py
```

Problem numbers are zero-padded to four digits. Shared TypeScript helpers belong in
`src/typescript/data_structures/`; ambient declarations for types supplied by the judge belong in
`src/typescript/judge-types.d.ts`. Reusable Python helpers should remain explicit and close to
their consumers unless several solutions genuinely share them.

## Toolchain

`mise.toml` pins the versions used by this repository:

| Tool | Version | Purpose |
| --- | ---: | --- |
| Node.js | 26.7.0 | TypeScript runtime and tooling |
| pnpm | 11.20.0 | JavaScript package manager and task runner |
| Python | 3.14.7 | Python solutions and repository scripts |
| uv | 0.12.2 | Python environment and dependency management |

TypeScript uses Vitest for tests and Biome for linting and formatting. Python uses pytest for
tests and Ruff for linting and formatting. TypeScript dependencies are locked in
`pnpm-lock.yaml`; Python dependencies are locked in `uv.lock`.

The local TypeScript compiler and Node.js tooling stay independently pinned, while solution code
targets ES2024 to match the language target documented by LeetCode's TypeScript judge. See
[LeetCode's current language environments](https://support.leetcode.com/hc/en-us/articles/360011833974-What-are-the-environments-for-the-programming-languages).

Keep this repository in the WSL filesystem, for example `~/prj/leetcode`, rather than under
`/mnt/c`. Git, dependency installation, test discovery, and file watching are substantially
faster on ext4.

## Initial setup

Install and activate `mise` for your shell using its
[official getting-started guide](https://mise.jdx.dev/getting-started.html), then run from the
repository root:

```bash
mise trust
mise install
pnpm install --frozen-lockfile
uv sync --frozen
pnpm prepare
```

`pnpm prepare` installs the Husky pre-commit hook explicitly. The hook runs
`mise exec -- pnpm ready`, so commits use the repository's pinned tools even if the interactive
shell has different global versions. Run `pnpm prepare` again if `lc doctor` reports that
`core.hooksPath` is not `.husky/_`.

Once `mise` is activated in the shell and this repository is trusted, its configuration adds
`bin/` to `PATH`. That makes the repository-local `lc` command available from the repository and
its subdirectories without a global installation.

These are the first-time project-tooling exceptions to the `lc` workflow: `mise`, pnpm, uv, and the
Git hook must exist before the repository-local command can run. Normal Git commit, push, and pull
operations also remain regular Git commands.

Verify the workspace after `lc` is available:

```bash
lc doctor
```

Confirm the active tools when troubleshooting setup:

```bash
mise current
node --version
pnpm --version
python --version
uv --version
```

### VS Code and WSL

Open the repository through VS Code's WSL support, accept the workspace extension
recommendations, and use `${workspaceFolder}/.venv` as the Python interpreter. The Testing view
then provides pytest and Vitest run/debug controls. Workspace tasks also expose new-problem
scaffolding, current-test-file runs, watch mode, formatting, and the complete `ready` gate.

## `lc` command reference

Run `lc`, `lc help`, or `lc --help` to display the built-in reference. `lc COMMAND --help` displays
the same reference without starting the command. Both `ts`/`typescript` and `py`/`python` are
accepted as language names. URL scaffolds and explicit problem IDs default to TypeScript. Test
paths infer their language from the extension, while commands without a target use the detected
problem language.

### Create problems

| Command | Behavior |
| --- | --- |
| `lc URL` | Fetch metadata, create and check out the problem branch, then scaffold TypeScript |
| `lc py URL` | Run the same automatic workflow for Python |
| `lc new URL` | Explicit spelling of the automatic TypeScript URL workflow |
| `lc new [LANG] ID TITLE...` | Create a manual, file-only scaffold; accepts `--url URL` and `--signature SIGNATURE` |

The automatic URL workflow requires a clean worktree and creates `feat/p-####-slug`. It refuses
duplicate IDs or branches and rolls the branch back if file generation fails. The manual workflow
does not perform Git operations.

### Test and submit

| Command | Behavior |
| --- | --- |
| `lc test` | Test the current problem; run all TypeScript and Python tests if none is detected |
| `lc test ID` | Test one TypeScript problem |
| `lc test LANG ID` | Test one problem in the selected language |
| `lc test LANG` | Run the complete suite for one language |
| `lc test PATH` | Infer the language from `.ts` or `.py` and test that file |
| `lc test all` / `lc test-all` | Run all TypeScript and Python tests explicitly |
| `lc test --watch` / `lc watch` | Watch the current TypeScript problem; watch all TypeScript tests if none is detected |
| `lc watch ID` / `lc watch PATH` | Watch one TypeScript problem or test file |
| `lc submit [LANG] [ID]` | Print judge-ready source; use the current problem when the ID is omitted |
| `lc submit [LANG] [ID] --copy` | Print the submission and copy it to the system clipboard |
| `lc copy [LANG] [ID]` | Short, readable form of `lc submit ... --copy` |

Relative test paths are resolved from the directory where `lc` was invoked, even though commands
run with the repository root as their working directory. Watch mode is intentionally TypeScript
only. Submission output remains clean so it can be redirected or pasted directly into LeetCode.

### Check the project

| Command | Behavior |
| --- | --- |
| `lc ready` | Reject incomplete scaffolds, then run the complete quality gate |
| `lc check` | Check formatting, lint, TypeScript types, and all tests |
| `lc format [LANG]` | Apply Biome and/or Ruff formatting |
| `lc format [LANG] --check` | Check formatting without changing files |
| `lc format check` / `lc format-check [LANG]` | Alternative spellings of the read-only format check |
| `lc lint [LANG]` | Run both linters or only the selected language's linter |
| `lc typecheck` | Type-check TypeScript without emitting files |
| `lc incomplete` | Report untouched generated markers |
| `lc doctor` | Verify pinned tools, dependencies, and the Git-hook installation |

`lc format` is the only mutating quality command. The other quality commands are read-only.
Failures from the underlying test and quality tools keep their original exit status.

### Detection and aliases

For commands with an optional problem ID, `lc` detects context in this order:

1. A problem directory containing the shell's original working directory.
2. A strict current branch named `feat/p-####-slug` with a matching local problem directory.
3. No current problem. `lc test` then runs all tests, while `lc submit` asks for an ID.

An explicit language or ID always wins. If a detected branch has both language implementations,
TypeScript wins because it is the project default.

| Short form | Full command |
| --- | --- |
| `lc t` | `lc test` |
| `lc w` | `lc watch` |
| `lc s` | `lc submit` |
| `lc r` | `lc ready` |
| `lc c` | `lc check` |
| `lc fmt` / `lc f` | `lc format` |
| `lc fc` | `lc format-check` |
| `lc n` / `lc add` / `lc a` | `lc new` |
| `lc d` | `lc doctor` |
| `lc types` | `lc typecheck` |

The longer compatibility spelling `lc submission` also maps to `lc submit`. The underlying pnpm
scripts remain available as low-level interfaces for automation or unusual runner arguments, but
normal interactive use should require only `lc`.

## Solve a problem

### 1. Read the contract

Before writing code, record:

- the exact function, method, or class signature;
- input constraints and important boundaries;
- whether the input may be mutated;
- whether output order matters;
- the expected time and auxiliary-space complexity.

Use every supplied example as a test, then add focused cases for empty or singleton inputs,
duplicates, zero, negative values, boundaries, and mutation semantics when the contract permits
them.

### 2. Create a problem with `lc`

```bash
lc https://leetcode.com/problems/search-insert-position/  # TypeScript by default
lc py https://leetcode.com/problems/search-insert-position/
```

`lc` is the preferred new-problem workflow. It fetches official LeetCode metadata, including
the ordinary-function signature, creates `feat/p-####-slug` from the current clean `HEAD`, checks
out that branch, then scaffolds the solution and test files.

It requires the setup above, a clean Git worktree, and network access to LeetCode. It deliberately
refuses to create a branch over uncommitted work. The automatic signature workflow currently
supports ordinary functions with self-contained signatures. Use the manual flow below for
design-class problems (constructors and operation sequences), signatures that need extra custom
type declarations, or whenever metadata discovery is unavailable.

### 3. Create a manual scaffold when needed

```bash
lc new 1512 "Number of Good Pairs"       # TypeScript by default
lc new py 1512 "Number of Good Pairs"
```

Use `lc new [py|ts] ID TITLE...` when working offline, for a design-class problem, or when the
URL workflow cannot derive the signature. It also accepts `--url URL` and `--signature SIGNATURE`
for explicit metadata. The manual scaffold:

- validates the language, number, and title;
- creates the zero-padded problem directory and two files;
- refuses a duplicate problem number or an existing target;
- prints the suggested branch and focused test command;
- performs no Git operations.

Generated tests are skipped deliberately, and generated sources contain incomplete markers.
Replace all placeholders while implementing the problem. `lc incomplete` reports any scaffold
markers that remain.

### 4. Implement the LeetCode signature

Keep the local implementation close to the code submitted to LeetCode:

- Python solutions normally expose the required camelCase method on `Solution`, or implement the
  design class requested by the problem.
- TypeScript solutions use named exports so their colocated Vitest tests can import them.
- TypeScript solution files avoid repository imports; test and helper imports include the
  explicit `.js` extension. Judge-provided `ListNode` and `TreeNode` types are declared ambiently.
- Completed solutions include a concise `time: O(...)` / `space: O(...)` comment.

Avoid local CLI parsing, test-only branches, or behavior that will not exist in the submitted
solution.

### 5. Run focused tests while iterating

```bash
# From a problem directory, or on its feat/p-####-slug branch
lc test

# An explicit TypeScript problem (the default language)
lc test 1512

# An explicit Python problem
lc test py 1512

# TypeScript watch mode
lc test --watch
lc watch
```

When LeetCode reports a failing input, add it as a regression test before changing the solution.
Confirm the test fails for the same reason, fix the implementation, then run the focused and
complete suites.

`lc test` identifies the current problem from the caller's problem directory or a strict
`feat/p-####-slug` branch. Outside either context, it runs the full TypeScript and Python suite.

### 6. Run the quality gate

```bash
lc ready
```

`lc ready` first rejects untouched scaffold markers, then checks formatting, linting,
TypeScript types, and both test suites. It is the preferred command before committing or
submitting.

Use narrower commands when diagnosing a failure:

| Command | Purpose |
| --- | --- |
| `lc test [LANG] [ID\|PATH]` | Test the current problem or all tests; explicit IDs default to TypeScript |
| `lc test --watch` / `lc watch [ID\|PATH]` | Watch the current TypeScript problem or a TypeScript file |
| `lc submit [LANG] [ID] [--copy]` | Render judge-ready source |
| `lc copy` | Render and copy the current solution |
| `lc incomplete` | Find untouched scaffold markers |
| `lc format [LANG] [--check]` | Apply formatting, or check without modifying files |
| `lc lint [LANG]` | Run linting |
| `lc typecheck` | Run TypeScript without emitting files |
| `lc check` | Run formatting checks, linting, types, and tests |
| `lc ready` | Require complete scaffolds, then run `lc check` |
| `lc doctor` | Verify tools, dependencies, and the Git-hook installation |

Review changes after any formatting command:

```bash
git diff --check
git diff
git status --short
```

### 7. Submit and save the accepted solution

Render the exact source intended for the judge:

```bash
lc submit ts 268
lc submit py 1512 --copy
# Or, from the current problem:
lc copy
```

The TypeScript renderer removes supported top-level module exports and refuses module imports,
CommonJS module syntax, triple-slash references, or unsupported export forms rather than
guessing. Python source is emitted unchanged. Always preserve the exact signature expected by
the judge.

After acceptance:

1. Keep any regression tests discovered while debugging.
2. Confirm the complexity comment matches the final algorithm.
3. Run `lc ready` again.
4. Commit the focused problem directory and push the branch.

```bash
git add src/typescript/p_1512_number_of_good_pairs
git commit -m "feat(1512): number of good pairs"
git push -u origin HEAD
```

Use the equivalent Python path for a Python solution. A pull request should link the problem,
summarize the algorithm and complexity, and record the validation command.

GitHub Actions runs the same frozen setup and quality gate for pushes and pull requests to `main`.

## License

This repository is licensed under the terms in [LICENSE](LICENSE).
