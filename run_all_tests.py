# run_all_tests.py
# Backend 37: runs every test_*.py file, one after the other, and prints one
# summary line per file. No new library is needed (no pytest).
#
# Run it with:   python run_all_tests.py            (run everything)
#                python run_all_tests.py cache fov  (only files whose name contains
#                                                    "cache" or "fov")
# Start the server first (uvicorn main:app --reload, other terminal) if you also
# want the server parts to run; without it they print SKIPPED.
#
# How a file is judged (our tests print their own PASS / FAIL lines and do not
# set an exit code, so the lines are counted):
#   FAIL    a line starting with "FAIL", a "check(s) FAILED" line, a crash
#           (non-zero exit code), or no answer within TIMEOUT_SECONDS
#   SKIPPED the file said it could not run (server off, files missing)
#   OK      everything else
# The exit code of this script is 1 if any file is FAIL, so it can be used
# before a commit.

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
TIMEOUT_SECONDS = 300


def run_one(path):
    """Run one test file. Returns (status, passes, fails, seconds, output)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    start = time.time()
    try:
        done = subprocess.run([sys.executable, path.name], cwd=HERE, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "FAIL", 0, 0, time.time() - start, f"No answer within {TIMEOUT_SECONDS} seconds."
    seconds = time.time() - start
    output = done.stdout + done.stderr
    lines = output.splitlines()
    passes = sum(1 for line in lines if line.startswith("PASS"))
    fails = sum(1 for line in lines if line.startswith("FAIL")) + sum(1 for line in lines if "check(s) FAILED" in line)
    if "Cannot reach the server" in output and done.returncode != 0:
        return "SKIPPED", passes, fails, seconds, output          # test_frames_api.py needs the server
    if fails or done.returncode != 0:
        return "FAIL", passes, fails, seconds, output
    if passes == 0 and any(line.startswith("SKIPPED") for line in lines):
        return "SKIPPED", passes, fails, seconds, output
    return "OK", passes, fails, seconds, output


def main():
    wanted = [a.lower() for a in sys.argv[1:]]
    files = sorted(HERE.glob("test_*.py"))
    if wanted:
        files = [f for f in files if any(w in f.name.lower() for w in wanted)]
    if not files:
        print("No test files found.")
        return 1

    results = []
    for path in files:
        print(f"running {path.name} ...", flush=True)
        results.append((path.name, *run_one(path)))

    print("\n" + "=" * 70)
    print(f"{'file':<28}{'status':<9}{'PASS':>6}{'FAIL':>6}{'seconds':>9}")
    for name, status, passes, fails, seconds, _output in results:
        print(f"{name:<28}{status:<9}{passes:>6}{fails:>6}{seconds:>9.1f}")
    print("=" * 70)

    failed = [r for r in results if r[1] == "FAIL"]
    for name, _status, _p, _f, _s, output in failed:
        print(f"\n--- the lines of {name} that went wrong (last 25 lines of its output) ---")
        print("\n".join(output.splitlines()[-25:]))

    skipped = [r[0] for r in results if r[1] == "SKIPPED"]
    if skipped:
        print("\nSkipped (server or files missing): " + ", ".join(skipped))
    print(f"\n{len(results) - len(failed)} of {len(results)} test files OK.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())