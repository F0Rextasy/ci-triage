---
name: ci-triage
description: Classifies a failed CI run -- regression, flaky, infra, dependency, or config -- from the log alone plus local git history. Use when a CI job goes red and someone must decide whether to block the merge, rerun the job, or fix the pipeline. No model, no API, no telemetry: the log never leaves the machine, and exit 1 means only one thing -- a real regression.
license: MIT
compatibility: Requires Python 3.8+ and git (only for the pre-existing check). Runs in Claude Code, Codex, Cursor, and any Agent Skills compatible client.
metadata:
  author: F0Rextasy
  version: "1.0"
---

# ci-triage

CI is red. The first question is always the same: *flaky test, infra blip,
or a real regression that should block the merge?* Answering by hand means
reading hundreds of log lines - and sending them to a model costs minutes
and leaks your build output. Every answer here comes from the log, an
optional local history, and git. Deterministic, offline, milliseconds.

## The one rule

You may not classify a red build by vibes:

```bash
python scripts/ci-triage "$LOG" --history .ci/triage.json --base origin/main
```

- **exit 1** - regression: your diff broke it, fix before merge.
- **exit 0** - not a merge blocker (flaky / pre-existing / infra /
  dependency / config / unknown): rerun or route elsewhere.
- **exit 2** - usage error.

`--strict` makes any warning block too.

## Protocol

1. **Grab the log** - the raw CI job log (file, or pipe to stdin).
2. **Classify** with the three inputs you have:

```bash
python scripts/ci-triage job.log --history .ci/triage.json --base origin/main --strict
```

3. **Act on the class**, not the noise:

| Class | Meaning | Action |
| --- | --- | --- |
| `regression` | code-level failure inside your diff | fix before merge |
| `pre-existing` | failing code untouched by `base...HEAD` | not your PR; file/fix separately |
| `flaky` | same normalized signature already in history | rerun, then quarantine the test |
| `infra` | timeout / 429 / OOM / runner died | rerun the job |
| `dependency` | resolution failed (pip/npm/cargo) | fix the lockfile, not the code |
| `config` | command not found, permission, missing secret | fix the pipeline |
| `unknown` | nothing matched | a human reads the log |

4. **Report back** - class, signature, the exact command, exit code.

## How it decides (three inputs, in order)

1. **Environment signatures** - infra, dependency, and config patterns are
   checked first: your code is not guilty of a `429`.
2. **History** (`--history FILE`) - a SHA-256 of the normalized failure
   excerpt (durations, SHAs, and paths stripped). Seen before -> `flaky`.
   The file is a plain local JSON counter; it is the only state, and it
   never leaves the machine.
3. **Git** (`--base REF`) - paths extracted from the traceback. None of
   them in `base...HEAD` -> `pre-existing`. Otherwise -> `regression`.

Order matters: environment beats history beats git beats "it looks like
code". The verdict is a pure function of (log, history, file) - same inputs,
same answer, no sampling.

## Hard bans

- Never paste CI logs into a chat/model to classify them - that is this
  skill's whole reason to exist.
- Never call `regression` on an `infra` signature to sound decisive.
- Never mark `flaky` without the history entry that proves it repeated.

## Reporting back

1. **Class** and signature.
2. **Command** and exit code:

```console
$ python scripts/ci-triage job.log --history .ci/triage.json --base origin/main
ci-triage: regression (signature 4f0c2a91b3e7d158, 1 failing, 0 warnings)
[exit 1]
```

3. **Action taken** - fixed, rerouted, or rerun - per the table above.
