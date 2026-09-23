# ci-triage

**CI is red: flaky test, infra blip, or a real regression?** `ci-triage`
answers from the log alone - plus your local git history - in
milliseconds, offline. No model reads your build output, no API key, no
telemetry: **exit 1 means exactly one thing, a regression your diff
caused.** Everything else exits 0 and tells you where to route it.

## Why this exists

Every CI triage tool shipped in 2026 sends the log to an LLM (Anthropic
API few-shot, "AI root cause", hosted services): minutes per verdict,
dollars per month, and your source paths in someone's prompt. But the
first three answers were never a judgment call - a `429` is infra, a pip
resolution error is dependency, `command not found` is config. Those are
**regex over the log**. The two hard questions have cheap deterministic
answers too: *seen this exact failure before?* (local signature history)
and *does the failing code even sit in my diff?* (git).

| Gate | Catches |
| --- | --- |
| **preflight** | `prod` in debug, `example.com` URLs, wildcard CORS, flat `requirements` |
| **prove-it** | claims (`all tests pass`) with no executed command + exit code behind them |
| **testgate** | tests that can never fail - the green that proves nothing |
| **shipcheck** | empty/mislabeled wheels, unimportable artifacts |
| **dsh-gate** | red turns closing green in DeepSeek Harness |
| ci-triage: classify red CI without an LLM *(this repo)* | merge blocked by a "regression" that is really a flake or a runner blip |

Family contract: one Python script, stdlib + git, exit 0 = not a merge
blocker, 1 = regression (blocks), 2 = usage error.

## Install

```bash
git clone https://github.com/F0Rextasy/ci-triage
python scripts/ci-triage job.log --history .ci/triage.json --base origin/main
```

In CI (`.github/workflows` step after a failed job):

```yaml
- if: failure()
  run: |
    gh run view ${{ github.run_id }} --log-failed > job.log
    python scripts/ci-triage job.log --history .ci/triage.json --base origin/main
```

Pipe logs in (`-` or no argument), or pass a file. `--format json` for
machines, `--strict` to block on warnings too.

## The seven classes

| Class | Severity | Decided by | Action |
| --- | --- | --- | --- |
| `regression` | **fail** | code marker in log + failing path inside your diff | fix before merge |
| `pre-existing` | warn | `git diff --base...HEAD` never touches the failing paths | not your PR |
| `flaky` | warn | normalized signature already in `--history` | rerun, quarantine |
| `infra` | warn | timeout / 429 / 503 / OOM / runner died | rerun |
| `dependency` | warn | pip/npm/cargo resolution failure | fix lockfile |
| `config` | warn | command not found / permission / missing secret | fix pipeline |
| `unknown` | warn | no pattern matched | human reads the log |

First match wins, in order: **environment -> history -> git -> code ->
unknown**. Your code is not guilty of a `429`, and nothing gets called
`regression` without either a code signature or a failing path inside the
diff. Full catalogue: [references/RULES.md](references/RULES.md).

The signature is a SHA-256 of the failure excerpt with churn stripped
(durations, SHAs, URLs, paths), so the same test failing twice hashes the
same and lands as `flaky`.

## Evidence (real outputs)

Regression fixture - blocks the merge:

```console
$ python scripts/ci-triage examples/regression.log --no-color
L1    FAIL  regression     code-level failure signature in the log

ci-triage: regression (signature 93aa4f7b5da8bd20, 1 failing, 0 warnings)
ci-triage: your change broke this -- fix it before merge
[exit 1]
```

Infra fixture - rerun, do not block:

```console
$ python scripts/ci-triage examples/infra.log --no-color
L3    WARN  infra          matched infra signature: timed out after

ci-triage: infra (signature 6f1efaa8e3b2500a, 0 failing, 1 warning)
ci-triage: not a merge blocker; use --strict to fail on warnings too
[exit 0]
```

The same log with `--history` twice - second sighting is a flake, not a
regression:

```console
$ python scripts/ci-triage examples/regression.log --history hist.json   # 1st
[exit 1] regression
$ python scripts/ci-triage examples/regression.log --history hist.json   # 2nd
L1    WARN  flaky          signature 93aa4f7b5da8bd20 already recorded 1 time(s)
[exit 0] flaky
```

Contract tests, 8 for 8 (one builds a real git repo to prove the
`pre-existing` rule):

```console
$ python -m unittest discover -s tests -v
........
----------------------------------------------------------------------
Ran 8 tests in 1.156s

OK
[exit 0]
```

## Layout

```text
ci-triage/
+-- scripts/ci-triage       # the classifier (stdlib + git, no network)
+-- SKILL.md                # Agent Skill (Claude Code / Codex / Cursor)
+-- examples/*.log          # fixtures: infra, dependency, config, regression, unknown
+-- references/RULES.md     # decision order, signature formula, exit codes
+-- tests/test_ci_triage.py # contract tests driving the real CLI + git
```

## License

[MIT](LICENSE)
