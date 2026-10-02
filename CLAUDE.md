# Repository Guide

## Layout

Solutions live under `src/typescript/` and `src/python/`, grouped as `p_####_<slug>/`.
TypeScript uses `<stem>.ts` and `<stem>.test.ts`; Python uses `<stem>.py` and `test_<stem>.py`.
Preserve the supported legacy problem/test names. Workflow commands live in `scripts/`, with
pytest coverage in `tests/`.

Each language's `data_structures/` contains only `ListNode`, `TreeNode`, and plain list/tree
conversion functions. Keep node classes separate from test helpers. See
[docs/data-structures.md](docs/data-structures.md). Submitted solutions use judge-provided types;
TypeScript ambient declarations live in `src/typescript/judge-types.d.ts`.

## Setup and workflow

Use `./bin/setup --trust` as the setup entry point. It trusts this mise configuration, installs
the pinned tools, synchronizes frozen dependencies, installs Playwright Chromium, and installs
Lefthook. `.node-version` pins Node; `package.json` and `mise.toml` pin pnpm; `mise.toml` pins
Python/uv. Dependencies are pinned and locked in `pnpm-lock.yaml` and `uv.lock`.
`.judge-node-version` pins the additional Node runtime used for judge compatibility;
`typescript-judge` in `package.json` pins the judge compiler. Setup and CI install both runtimes.

The everyday workflow is **start → solve → `lc done`**, on `main`:

- `lc` opens the numbered menu and shows the active problem/language. Enter never submits.
- `lc new` prompts for a URL and language. `lc URL` starts TypeScript; `lc py URL` starts Python.
  Starting fetches official signatures/examples; reopening activates existing files unchanged.
- `lc test` tests the active problem. `lc live` watches TypeScript tests. Forward runner options
  after `--`, for example `lc test -- -k boundary`. `lc test all` runs both languages.
- `lc list [ts|py] URL` imports a problem list in website order; `lc list` shows progress and
  `lc list --refresh` updates the snapshot. `lc next [ts|py]` opens the first unsolved problem.
  Repeat Next before Accepted to reopen the same files. Count remote Accepted at import and
  local Accepted submissions in either language; file existence and passing local tests do not
  mark a problem solved. Import/refresh use the saved session and never modify remote lists.
  Keep one snapshot in `.lc/practice.json`, with atomic replacement only after complete fetching.
  Support `/problem-list/` URLs; Study Plans and premium scaffolding remain unsupported.
- `lc done [ts|py] [ID]` requires main and no unrelated staged changes, formats the current
  problem, runs `lc ready`, submits, waits, then commits/pushes only after Accepted.
- `lc login` gives numbered browser steps and separate hidden prompts for the `LEETCODE_SESSION`
  and `csrftoken` values. The first prompt also accepts a complete Cookie header.
  `lc login --check` validates without interaction; `lc logout` removes local credentials only.
- `lc show` prints judge-ready source; `lc copy` copies it. Both check focused tests first.
- `lc help COMMAND` gives focused help. Keep older commands/aliases compatible: `watch` means
  `live`, `submit` means `show`, and `finish` means `done`.

Resolve explicit targets before caller-directory context, ignored `.lc/active.json`, and legacy
problem branches. TypeScript is the default for a new explicit ID or URL. Never create problem
branches automatically. Noninteractive commands must not prompt.

`lc new [ts|py] ID TITLE... [--url URL] [--signature SIG]` remains the manual scaffold fallback.
Generate assertions only for ordinary JSON examples with clear return values. Keep editable
skipped templates for mutations, nodes, design classes, or special judging.

## Submission state and session

Default submissions use direct HTTP with cookies imported by `lc login`. Validate before
atomically storing `.lc/session.json` with mode `0600`; keep `.lc/` mode `0700`. Never accept
credentials through arguments or stdin, or print session data. Expiry/challenges require the
user's normal browser interaction and fresh import; cookie import is not a guaranteed bypass.
`lc done --browser` explicitly selects pinned Python Playwright with its persistent profile
under ignored `.lc/browser/`. Login/challenges require the user's normal interaction.
Journal submission IDs, source hashes, verdicts, and Git progress under `.lc/submissions/`.
Whitelist optional runtime, memory, test-count, and percentile metrics in each attempt's result.
Show the saved summary and submission link on retries without fetching metrics or resubmitting.
Keep old journals compatible and omit unavailable or malformed optional metrics.
Write state atomically and serialize `done` processes. An uncertain POST must not automatically
resubmit. `lc done --resume ID` verifies remote identity/source before resuming;
`--retry-uncertain` is explicit recovery after the user checks history for a missing submission.

Preserve unrelated edits and reject unrelated staged changes. Verify the saved source matches
the accepted submission. Retries of judging/committing/pushing must not duplicate accepted
submissions or commits. Keep the existing pre-commit hook and CI checks enabled.

## Quality commands

- `lc ready`: unfinished-scaffold detection, then the complete check gate. Required before
  submitting; run by the commit hook and CI.
- `lc check`: format checks, lint, TypeScript types, judge compatibility, and all Vitest/pytest tests.
- `pnpm judge:check`: type-check actual rendered submissions with TypeScript 5.7.3 and run the
  TypeScript suite with Node 22.14.0. Exclude test globals from rendered-source checking and
  isolate each problem's declarations. Keep repository tooling on its separate newer pins.
- `lc format [ts|py] [--check]`, `lc lint [ts|py]`, `lc typecheck`: individual checks.
- `lc incomplete`: list unfinished scaffold markers.
- `lc doctor`: inspect tools, dependencies, and hooks.

Stable low-level interfaces remain in `package.json`. Use `pnpm ready:all` for CI-equivalent
verification. Tests of submission transitions use fake judge results and real temporary local
Git repositories; keep them independent of network, authentication, and the user's origin.

## Style and tests

Use four spaces, UTF-8, final newlines, and no trailing whitespace. Prefer straightforward loops
and clear names. Keep explicit `.js` extensions in relative TypeScript imports. Solution source
must avoid TypeScript module imports, CommonJS, and triple-slash references so the existing
submission renderer can produce self-contained source. Prefer named exports and ES2024 APIs.
Completed solutions include concise `time: O(...)` / `space: O(...)` comments. Python normally
uses `Solution` and LeetCode-compatible camelCase methods.

Cover examples and meaningful boundary cases. Replace generated skipped placeholders with real
tests. For helpers, cover empty/singleton/duplicate/sparse inputs, round trips, and input
preservation. For workflow changes, cover CLI compatibility, target selection, and failure
recovery. Run authenticated browser acceptance through the browser role when changing submission.

## Commits

Work on `main`. Use short Conventional Commit subjects such as
`feat(0035): search insert position`. `lc done` does not create a PR/MR. If separately requested,
omit `[codex]` from its title. Its description contains only `Closes ISSUE-ID`, or is empty when
no issue ID exists, unless the user explicitly asks for more. Report validation in chat.
