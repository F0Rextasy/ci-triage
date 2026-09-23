# Rule catalogue

`scripts/ci-triage` reads one failed CI log and returns exactly one
**class**. Every rule answers one question: *who is responsible for this
red build - the diff, the test, the runner, the registry, or the
pipeline?*

One verdict per log, decided in this order. The first match wins; later
inputs are never consulted once an earlier one answers.

## 1. Environment classes (checked first)

| Class | Severity | Log contains (first match wins) |
| --- | --- | --- |
| `infra` | warn | `timed out after`, `connection reset`, `could not resolve host`, `429`/`502`/`503`, `no space left`, `out of memory`, `runner terminated`, `HTTP/1.1 5xx` |
| `dependency` | warn | `could not find a version that satisfies`, `no matching distribution`, `ERESOLVE`, `err! etarget`, lockfile conflicts |
| `config` | warn | `command not found`, `is not recognized as`, `permission denied (chmod)`, `missing environment variable`, `secret.*not set` |

Your code is not guilty of a `429`: environment rules precede every code
rule, and the finding points at the matched line in the log.

## 2. History: `flaky` (warn)

Signature = SHA-256 of the first three failure-looking lines (matching
`assert|expected|error|failed|failure|panic|fail`), normalized: lowercased,
durations (`0.42s`, `132ms`), SHAs (7-40 hex), URLs, and paths stripped to
`#`, whitespace collapsed, capped at 200 chars, hashed to 16 hex chars.

- First sighting with `--history FILE`: recorded as count 1, decision falls
  through to git/code.
- Signature already present: class `flaky`, counter incremented.

Without `--history` the flaky rule cannot fire - never claimed without the
record that proves it repeated.

## 3. Git: `pre-existing` (warn)

With `--base REF` (and `--repo DIR`, default `.`): `git diff --name-only
REF...HEAD` gives the changed set; source paths are extracted from the
log's traceback shapes (`File "..."`, `--> path:line`, `at path:line`,
`path.ext:12:5`) and kept only when the file exists inside the repo.

Failing paths exist, none is in the changed set -> `pre-existing`: broken
on the base too, not introduced by this diff. Git unavailable (bad ref,
not a repo) -> the check is skipped silently and the code rules apply.

## 4. Code: `regression` (fail)

The log matches a code-failure marker (`AssertionError`, `traceback (most`,
`type error TSnnnn`, `error[E...]`, `panic:`, `expected ... to be`, test
runner summaries) -> `regression`. This is the only class that blocks by
default: exit 1.

## 5. `unknown` (warn)

No failure markers at all, or failure-shaped output without any recognized
pattern. Exit 0 (a human reads the log); exit 1 with `--strict`. The gate
never guesses a confident class it cannot support.

## Escape hatch

None: classification is evidence-based by construction. Annoyed by a
repeat? Fix the flaky test (that is the point) or drop `--history`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | not a merge blocker: any warn class without `--strict` |
| `1` | `regression`, or any warning with `--strict` |
| `2` | usage error - unreadable log, no log on a non-tty stdin, bad flags |
