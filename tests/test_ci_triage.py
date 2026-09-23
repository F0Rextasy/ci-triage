"""Contract tests for ci-triage. Run: python -m unittest discover -s tests -v

Every test drives the real CLI against fixture logs (and a real temp git
repo for the pre-existing rule) and asserts the observable exit code,
classification, and JSON -- nothing internal.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "ci-triage")
EXAMPLES = os.path.join(ROOT, "examples")


def run_cli(*args, cwd=None):
    proc = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=cwd or ROOT,
    )
    return proc.returncode, proc.stdout, proc.stderr


def git(repo, *args, env=None):
    full_env = dict(os.environ)
    full_env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                     "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    if env:
        full_env.update(env)
    subprocess.run(["git", "-C", repo, *args], check=True,
                   capture_output=True, env=full_env)


class CiTriageContract(unittest.TestCase):
    def test_infra_log_is_not_a_merge_blocker(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "infra.log"),
                               "--no-color")
        self.assertEqual(code, 0, out)
        self.assertIn("infra", out)
        self.assertIn("not a merge blocker", out)

    def test_dependency_log_classifies_dependency(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "dependency.log"),
                               "--format", "json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertEqual(data["class"], "dependency")

    def test_config_log_classifies_config(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "config.log"),
                               "--format", "json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["class"], "config")

    def test_regression_blocks_with_exit_one(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "regression.log"),
                               "--format", "json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(data["class"], "regression")
        self.assertEqual(data["counts"], {"fail": 1, "warn": 0})
        self.assertRegex(data["signature"], r"^[0-9a-f]{16}$")
        self.assertIn("suggestion", data["findings"][0])

    def test_history_turns_a_repeat_failure_into_flaky(self):
        with tempfile.TemporaryDirectory() as tmp:
            hist = os.path.join(tmp, "history.json")
            log = os.path.join(EXAMPLES, "regression.log")
            code, out, _ = run_cli(log, "--history", hist, "--format", "json")
            self.assertEqual(code, 1, out)  # first sighting: regression
            self.assertEqual(json.loads(out)["class"], "regression")
            code, out, _ = run_cli(log, "--history", hist, "--format", "json")
            self.assertEqual(code, 0, out)  # repeat: flaky, not a blocker
            data = json.loads(out)
            self.assertEqual(data["class"], "flaky")
            with open(hist, encoding="utf-8") as fh:
                stored = json.load(fh)
            self.assertEqual(list(stored.values()), [2])

    def test_preexisting_failure_untouched_by_the_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            os.makedirs(os.path.join(repo, "src"))
            for name in ("math_utils", "util"):
                with open(os.path.join(repo, "src", name + ".py"), "w") as fh:
                    fh.write("def f():\n    return 1\n")
            git(repo, "init", "-q")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "base")
            with open(os.path.join(repo, "src", "util.py"), "w") as fh:
                fh.write("def f():\n    return 2\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "change")

            untouched = os.path.join(tmp, "untouched.log")
            with open(untouched, "w", encoding="utf-8") as fh:
                fh.write('Traceback (most recent call last):\n'
                         '  File "src/math_utils.py", line 1\n'
                         'AssertionError: boom\n')
            code, out, _ = run_cli(untouched, "--base", "HEAD~1",
                                   "--repo", repo, "--format", "json",
                                   cwd=repo)
            self.assertEqual(code, 0, out)
            self.assertEqual(json.loads(out)["class"], "pre-existing")

            touched = os.path.join(tmp, "touched.log")
            with open(touched, "w", encoding="utf-8") as fh:
                fh.write('Traceback (most recent call last):\n'
                         '  File "src/util.py", line 1\n'
                         'AssertionError: boom\n')
            code, out, _ = run_cli(touched, "--base", "HEAD~1",
                                   "--repo", repo, "--format", "json",
                                   cwd=repo)
            self.assertEqual(code, 1, out)
            self.assertEqual(json.loads(out)["class"], "regression")

    def test_unrecognized_log_warns_and_strict_fails(self):
        code, out, _ = run_cli(os.path.join(EXAMPLES, "unknown.log"),
                               "--no-color")
        self.assertEqual(code, 0, out)
        self.assertIn("unknown", out)
        code, out, _ = run_cli(os.path.join(EXAMPLES, "unknown.log"),
                               "--no-color", "--strict")
        self.assertEqual(code, 1, out)

    def test_missing_log_is_usage_error(self):
        code, _, err = run_cli(os.path.join("nope", "missing.log"))
        self.assertEqual(code, 2)
        self.assertIn("cannot read log", err)


if __name__ == "__main__":
    unittest.main()
