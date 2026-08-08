# LeetCode solutions

A local TypeScript and Python workspace for solving LeetCode problems, reproducing failed
submissions, and validating examples and edge cases before submitting again.

Each problem keeps its implementation next to its tests. The repository pins its complete
toolchain, provides a safe scaffold for new problems, and exposes one command for the final
quality gate.

## Repository layout

```text
src/
├── python/
│   └── p_####_<slug>/
│       ├── p_####_<slug>.py
│       └── test_p_####_<slug>.py
└── typescript/
    ├── data_structures/
    └── p_####_<slug>/
        ├── p_####_<slug>.ts
        └── p_####_<slug>.test.ts
scripts/
├── check_incomplete.py
└── new_problem.py
tests/
├── test_check_incomplete.py
└── test_new_problem.py
```

Problem numbers are zero-padded to four digits. Shared TypeScript helpers belong in
`src/typescript/data_structures/`; reusable Python helpers should remain explicit and close to
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

Keep this repository in the WSL filesystem, for example `~/prj/leetcode`, rather than under
`/mnt/c`. Git, dependency installation, test discovery, and file watching are substantially
faster on ext4.

## Initial setup

From the repository root:

```bash
mise trust
mise install
pnpm install --frozen-lockfile
uv sync --frozen
```

`pnpm install` also installs the Husky pre-commit hook. The hook runs `mise exec -- pnpm check`,
so commits use the repository's pinned tools even if the interactive shell has different global
versions.

Confirm the active tools when troubleshooting setup:

```bash
mise current
node --version
pnpm --version
python --version
uv --version
```

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

### 2. Start from an up-to-date branch

```bash
git switch main
git pull --ff-only
git switch -c feat/p-1512-number-of-good-pairs
```

The usual branch format is `feat/p-####-slug`. Keep unrelated problem solutions in separate
branches and commits.

### 3. Generate the source and test pair

```bash
pnpm new ts 1512 "Number of Good Pairs" \
    --url https://leetcode.com/problems/number-of-good-pairs/

pnpm new py 1512 "Number of Good Pairs"
```

The URL is optional, but adding the canonical LeetCode problem URL keeps the source traceable.
The scaffold:

- validates the language, number, title, and optional URL;
- creates the zero-padded problem directory and two files;
- refuses to overwrite an existing problem;
- prints the suggested branch and focused test command;
- performs no Git operations.

Generated tests are skipped deliberately, and generated sources contain incomplete markers.
Replace all placeholders while implementing the problem. `pnpm incomplete` reports any scaffold
markers that remain.

### 4. Implement the LeetCode signature

Keep the local implementation close to the code submitted to LeetCode:

- Python solutions normally expose the required camelCase method on `Solution`, or implement the
  design class requested by the problem.
- TypeScript solutions use named exports so their colocated Vitest tests can import them.
- Relative TypeScript imports include the explicit `.js` extension.
- Completed solutions include a concise `time: O(...)` / `space: O(...)` comment.

Avoid local CLI parsing, test-only branches, or behavior that will not exist in the submitted
solution.

### 5. Run focused tests while iterating

```bash
# TypeScript
pnpm test:ts \
    src/typescript/p_1512_number_of_good_pairs/p_1512_number_of_good_pairs.test.ts

# TypeScript watch mode
pnpm test:ts:watch \
    src/typescript/p_1512_number_of_good_pairs/p_1512_number_of_good_pairs.test.ts

# Python
pnpm test:py \
    src/python/p_1512_number_of_good_pairs/test_p_1512_number_of_good_pairs.py
```

When LeetCode reports a failing input, add it as a regression test before changing the solution.
Confirm the test fails for the same reason, fix the implementation, then run the focused and
complete suites.

### 6. Run the quality gate

```bash
pnpm ready
```

`pnpm ready` first rejects untouched scaffold markers, then checks formatting, linting,
TypeScript types, and both test suites. It is the preferred command before committing or
submitting.

Use narrower commands when diagnosing a failure:

| Command | Purpose |
| --- | --- |
| `pnpm test` | Run all TypeScript and Python tests |
| `pnpm test:ts [path]` | Run all or selected Vitest tests |
| `pnpm test:ts:watch [path]` | Run Vitest in watch mode |
| `pnpm test:py [path]` | Run all or selected pytest tests |
| `pnpm incomplete` | Find untouched scaffold markers |
| `pnpm format:check` | Check Biome and Ruff formatting without modifying files |
| `pnpm format` | Apply Biome and Ruff formatting |
| `pnpm lint` | Run Biome and Ruff linting |
| `pnpm typecheck` | Run TypeScript without emitting files |
| `pnpm check` | Run formatting, linting, types, and tests |
| `pnpm ready` | Require complete scaffolds, then run `pnpm check` |

Review changes after any formatting command:

```bash
git diff --check
git diff
git status --short
```

### 7. Submit and save the accepted solution

Copy only the implementation and required helpers into the LeetCode editor. Preserve the exact
signature expected by the judge. Remove repository-only module syntax such as a TypeScript
`export` when it is not part of LeetCode's starter code; do not copy local tests or imports.

After acceptance:

1. Keep any regression tests discovered while debugging.
2. Confirm the complexity comment matches the final algorithm.
3. Run `pnpm ready` again.
4. Commit the focused problem directory and push the branch.

```bash
git add src/typescript/p_1512_number_of_good_pairs
git commit -m "feat(1512): number of good pairs"
git push -u origin HEAD
```

Use the equivalent Python path for a Python solution. A pull request should link the problem,
summarize the algorithm and complexity, and record the validation command.

## License

This repository is licensed under the terms in [LICENSE](LICENSE).
