# LeetCode solutions

TypeScript and Python solutions, with tests beside each problem. The everyday workflow is:
**start → solve → `lc done`**. Work stays on `main`.

## Setup

Install and activate [mise](https://mise.jdx.dev/getting-started.html), then run:

```sh
./bin/setup --trust
lc doctor
```

Setup installs the pinned tools, synchronizes the locked dependencies, installs Chromium for
Playwright, and installs the existing Git hook. It is safe to repeat. `mise.toml` adds `bin/`
to your path inside this repository; `./bin/lc` also works directly.

| Tool | Pin |
| --- | --- |
| Node.js | `.node-version` / `mise.toml` |
| LeetCode judge Node.js | `.judge-node-version` |
| pnpm | `package.json` / `mise.toml` |
| Python and uv | `mise.toml` |
| Vitest, Biome, TypeScript, Lefthook | `package.json` / `pnpm-lock.yaml` |
| pytest, Ruff, Python Playwright | `pyproject.toml` / `uv.lock` |

## Start, solve, finish

Run `lc` for a numbered menu. It shows the active problem and language and lets you start,
select, test, submit, or copy a solution. Choose **Done** explicitly to submit; pressing Enter
alone redisplays the menu.

```sh
lc new
# Or start directly (TypeScript is the default):
lc https://leetcode.com/problems/search-insert-position/
lc py https://leetcode.com/problems/search-insert-position/

# Edit the solution and add edge cases to its tests.
lc test
lc live                       # TypeScript tests on each change
lc done                       # Check, submit, commit, and push after Accepted
```

Starting fetches the official signature and examples. Ordinary JSON inputs with unambiguous
return values become runnable pytest/Vitest assertions. Mutation, nodes, design classes,
missing examples, and special judging rules get an editable skipped test with an explanation.
Unusual APIs include the official starter as a commented reference. Complete the solution,
replace skipped templates, and fill in its time/space complexity before finishing.

Starting an existing problem activates its files without overwriting them. Known URLs reopen
without network access; official URLs for legacy files are remembered in `.lc/problems/`.
Starting requires `main`; unrelated working files are preserved.

### Commands

| Command | Action |
| --- | --- |
| `lc` | Active problem and guided menu |
| `lc new` | Ask for a problem URL and language |
| `lc URL` / `lc py URL` | Start or reopen a problem |
| `lc list [ts\|py] URL` | Import a LeetCode practice list |
| `lc list` / `lc list --refresh` | Show the list or refresh it from LeetCode |
| `lc next [ts\|py]` | Start or reopen the next unsolved problem |
| `lc test [ts\|py] [ID\|PATH]` | Test one problem; all tests when no problem is detected |
| `lc live [ID\|PATH]` | Watch TypeScript tests |
| `lc done [ts\|py] [ID]` | Check, submit, commit, push |
| `lc login [--check]` | Import or validate a cookie session |
| `lc logout` | Remove saved local credentials |
| `lc copy [ts\|py] [ID]` | Check and copy judge-ready source |
| `lc show [ts\|py] [ID]` | Check and print judge-ready source |
| `lc help [COMMAND]` | General or command-specific help |

Targets resolve in this order: explicit arguments, the caller's problem directory, remembered
selection in ignored `.lc/active.json`, then a legacy `feat/p-####-*` branch. A language alone
with `lc test ts` or `lc test py` retains the existing whole-language test behavior.

Runner arguments after `--` pass through unchanged:

```sh
lc test py 35 -- -k boundary
lc test -- -t 'example'        # Vitest test-name filter
lc test all                   # All languages
lc test py all -- -x           # All Python tests, stop after a failure
```

`watch` aliases `live`; `submit` and `submission` retain their source-printing behavior as
aliases of `show`. `finish` aliases `done`. Older shortcuts still work: `t`, `w`, `s`, `r`, `c`,
`fmt`, `f`, `fc`, `n`, `add`, `a`, `d`, and `types`. Scripts can keep using the `pnpm` interfaces.
Noninteractive commands never wait for input; `lc new` needs a URL when stdin is not a terminal.

For an offline scaffold:

```sh
lc new py 35 Search Insert Position \
  --url https://leetcode.com/problems/search-insert-position/ \
  --signature 'searchInsert(self, nums: list[int], target: int) -> int'
```

### What `lc done` does

1. Display the target, require `main`, and reject unrelated staged changes.
2. Format only the current problem, then run `lc ready`: unfinished-scaffold detection,
   formatting checks, linters, TypeScript checking, judge compatibility, and the complete test suite.
3. Render the solution and submit it to LeetCode over HTTP using the saved cookie session.
4. Wait for Accepted. A rejection leaves your work uncommitted so you can fix it.
5. Stage only this problem, commit (for example, `feat(0035): search insert position`), and push
   the saved commit to `origin/main`. The commit hook runs as usual. There is no PR step.

The verdict includes a submission link and any runtime, memory, passed-test count, or percentile
that LeetCode returns. These metrics are saved locally and shown again when resuming a failed
commit or push. Missing metrics are omitted.

Before your first submission, run `lc login` in a local terminal and follow its numbered steps:

1. Sign in at `https://leetcode.com/` in your normal browser and check for your account avatar.
2. Right-click the page → Inspect. In Chrome or Edge, open Application → Storage → Cookies →
   `https://leetcode.com`. Firefox uses the Storage tab → Cookies.
3. Copy the **Value** of `LEETCODE_SESSION` into the first terminal prompt and press Enter.
4. Copy the **Value** of `csrftoken` into the second prompt and press Enter.

Paste values without names or quotes. Input stays invisible while you paste. If
`LEETCODE_SESSION` is missing, finish account sign-in and reload the page; completing a
Cloudflare challenge alone does not sign you in. Clear any cookie-table filter between lookups.

Keep cookies in the local terminal, outside chat, command arguments, and piped stdin. The
command validates the session and saves only those two cookies in ignored `.lc/session.json`
(unencrypted, mode `0600`, with `.lc/` mode `0700`). The first prompt also accepts a complete
Cookie header for compatibility with the earlier login instructions.

Run `lc login --check` to validate the saved session without prompts or opening a browser.
Run `lc logout` to remove local credentials; it does not sign out your website session.
Expired sessions and site challenges require interaction in your normal browser followed by
`lc login` again. Cookie import does not guarantee that LeetCode will allow HTTP requests.
Keep `.lc/` private: it contains credentials and local workflow state.

Use `lc done --browser` for the dedicated Playwright fallback. It reuses the persistent profile
in `.lc/browser/`; complete its login or challenges yourself. Noninteractive submissions fail
promptly when interaction is needed. Both backends preserve the recovery workflow below, and
an uncertain submission POST is never automatically retried.

### Interrupted submissions and saving

Run `lc done` again after a timeout, failed commit, or failed push. The journal in
`.lc/submissions/` records source hashes, submission IDs, verdicts, and saved commits. Retries
resume judging or saving without submitting accepted code again. Changes to the source while
judging prevent saving different code. Restore the submitted source before resuming that attempt.

An interrupted submission POST without a known ID has an uncertain outcome. Check your
LeetCode submission history, then use:

```sh
lc done --resume SUBMISSION_ID
```

This checks the remote submission's problem, language, and source before resuming. If history
confirms no submission was created, explicitly run `lc done --retry-uncertain`. Do not remove
the journal to retry: it is what prevents accidental duplicate submissions.

### Practice from a list

Copy a LeetCode **problem list** URL, then run:

```sh
lc list https://leetcode.com/problem-list/wpwgkgt/
lc next
# Solve the opened problem, then:
lc done
lc next
```

Use `lc list py URL` to practice in Python. Importing saves one list in website order; it does
not create every problem's files. `lc next` opens the first unsolved problem and uses the usual
scaffold and examples. Running it again before Accepted reopens that same problem unchanged.

`lc list` shows progress. Accepted submissions in either language count as solved, combining
LeetCode's status at import with the local submission journal. Run `lc list --refresh` after
solving on the website or changing a list, including a Smart List whose contents have changed.
Import and refresh use your saved `lc login` session. The snapshot lives in ignored
`.lc/practice.json`; your lists on LeetCode are unchanged. Study Plan URLs are not supported.
Premium questions remain in the list, but automatic scaffolding currently supports free problems.

## Helpers and layout

Problems use `src/typescript/p_####_<slug>/` or `src/python/p_####_<slug>/`, with matching source
and test filenames. Some older problems retain their original numeric padding/test names.
Workflow code lives in `scripts/`; workflow tests live in `tests/`.

The [list and tree reference](docs/data-structures.md) links matching TypeScript/Python node
classes and conversion functions. Nodes are separate from test helpers. Solutions use
LeetCode's judge-provided types; conversion helpers stay in tests.

## Quality commands

- `lc ready`: require completed scaffolds, then run every check. Used by the commit hook and CI.
- `lc check`: formatting, lint, types, judge compatibility, and tests, allowing unfinished scaffolds.
- `lc format [ts|py] [--check]`, `lc lint [ts|py]`, `lc typecheck`: individual checks.
- `lc incomplete`: list unfinished scaffolds.
- `lc doctor`: inspect the pinned tools, dependencies, and hook installation.

`pnpm judge:check` checks rendered TypeScript submissions with TypeScript 5.7.3 and runs the
TypeScript tests under Node 22.14.0, matching the versions in
[LeetCode's language environment guide](https://support.leetcode.com/hc/en-us/articles/360011833974-What-are-the-environments-for-the-programming-languages).
It runs automatically in `lc check`, `lc ready`, and `lc done`. Repository tooling keeps its
newer versions. The check covers your local tests and the bundled judge node types; LeetCode's
hidden tests and other judge-provided libraries still require a real submission.

See [CLAUDE.md](CLAUDE.md) for project conventions.
