#!/usr/bin/env python3
"""Hearth prop inventory publish check.

Compares the last-published commit SHA held in a local state file
against the newest commit on GitHub for the master prop inventory:

    production/hearth-prop-inventory.md
    in repo claypnw/mogollon-s-hearth-build-page

Verdicts (last line of output, exactly):
    VERDICT: MATCH    - state SHA matches GitHub; briefing says nothing
    VERDICT: CHANGED  - GitHub differs, or no/invalid state on file;
                        briefing asks the admin whether to publish
    VERDICT: UNKNOWN  - GitHub API could not be read; briefing skips silently

Exit codes:
    0 - MATCH
    0 - CHANGED
    2 - UNKNOWN

Note: the generic batch template names a "VERDICT: PASS" line; this
program's pass-equivalent is MATCH, per its specification, so its
final lines are MATCH / CHANGED / UNKNOWN.

Failure behaviour: any exception during the GitHub fetch -- including
a truncated reply (http.client.IncompleteRead) -- becomes UNKNOWN,
exit 2, with the verdict line printed and the run written to the
dated log. A top-level guard does the same for any other unexpected
error, so a run never ends in a bare traceback with no verdict.

An UNKNOWN verdict is a non-response: the check ran and no answer
came back. By the admin's ruling (2026-10-21) a non-response is a problem,
so an UNKNOWN verdict is also reported to the one shared error
program, shared_error.py -- an error record opens and its problem
entry is appended to the quality record in the same step. MATCH and
CHANGED are answers -- a MATCH says there is nothing to publish --
and are never reported.

State validity: a state value shorter than 7 characters, or one
containing non-hex characters, is never a MATCH; it is reported as
CHANGED with the reason stated.

With --mark-published, after a successful fetch the current full
GitHub SHA is written into the state file (for use AFTER a publish
completes). The write is atomic: the new value goes to a temp file in
the same directory and is then moved over the state file with
os.replace(), so the state file always holds a whole old or a whole
new SHA. The verdict printed in that run reflects the comparison
made BEFORE the state file was updated, and the output carries an
explicit "Marked published:" line recording the update.

Python 3 standard library only.
"""

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    PHOENIX = ZoneInfo("America/Phoenix")
except Exception:  # pragma: no cover - tzdata missing fallback
    # Arizona does not observe daylight saving; MST is UTC-7 year-round.
    PHOENIX = timezone(timedelta(hours=-7))

REPO = "claypnw/mogollon-s-hearth-build-page"
FILE_PATH = "production/hearth-prop-inventory.md"
API_URL = (
    "https://api.github.com/repos/claypnw/mogollon-s-hearth-build-page"
    "/commits?path=production/hearth-prop-inventory.md&per_page=1"
)
DEFAULT_STATE_FILE = Path.home() / (
    "workspace/goals/mogollon-s-hearth-skyrim-build-materials"
    "/hidden_files/prop-inventory-publish-state.md"
)
LOG_DIR = Path.home() / "workspace/batch-logs/hearth-publish-check"
TIMEOUT_SECONDS = 15
MIN_STATE_SHA_LEN = 7
HEX_DIGITS = set("0123456789abcdefABCDEF")

# --- Rule log (the admin's design, 2026-10-18) ---------------------------------
# This program writes its own rule-log marks via ~/workspace/batch/rulelog.py
# (design: ~/workspace/morning-post/RULE-LOG-DESIGN.md). Marks are decided by
# values this program itself computed — never by exit code alone and never
# by a default evidence string. Rule logging is additive only: it must never
# change this program's output or exit code, so every call is guarded and
# the writer's own prints are captured, not shown.
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import rulelog as _rulelog
except Exception:  # rule log unavailable — the program runs as before
    _rulelog = None

_RL_PATH = None
_RL_TOTAL = 0
_RL_LABELS = {}
_RL_ZERO = set()


def _rl_begin(batch, labels):
    global _RL_PATH, _RL_TOTAL, _RL_LABELS
    _RL_LABELS = dict(labels)
    _RL_TOTAL = len(labels)
    if _rulelog is None:
        return
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _rulelog.cmd_begin(batch, _rulelog.now().strftime("%Y-%m-%d"), _RL_TOTAL)
        _RL_PATH = buf.getvalue().strip().splitlines()[-1]
    except Exception:
        _RL_PATH = None


def _rl(kind, n, evidence=""):
    if _rulelog is None or _RL_PATH is None:
        return
    try:
        _rulelog.mark(_RL_PATH, n, _RL_LABELS.get(n, f"step_{n}"), kind, evidence)
        if kind == "FAIL":
            _RL_ZERO.add(n)
    except Exception:
        pass


def _rl_finish(failed):
    """Close the rule log. If the run ended UNKNOWN but no step stands
    at 0, put the last step at 0 with a generic reason — the program's
    own output carries the detail."""
    if _rulelog is None or _RL_PATH is None:
        return
    try:
        if failed and not _RL_ZERO and _RL_TOTAL:
            _rl("FAIL", _RL_TOTAL,
                "program reported failure at exit — see program output for the reason")
        with contextlib.redirect_stdout(io.StringIO()):
            _rulelog.cmd_close(_RL_PATH)
    except Exception:
        pass


# --- Shared error program (standards wiring step D, 2026-10-21) -------------
# The one shared error program is shared_error.py in this same
# directory (~/workspace/batch/). An UNKNOWN verdict -- the
# non-response case, where GitHub could not be read and the check
# returned no answer -- is reported to it, so an error record opens
# in the one place and its problem entry is appended to the quality
# record. The standard processing -- write the error down in full
# in the dated error record, open an ERROR line in the completion
# pile, hand back STOP -- happens in that one program, never in
# code copied here. This block is only the call. If the shared
# error program cannot be loaded or cannot record, the report
# prints a loud line on stderr and this program's own output,
# dated log, verdict line, and exit code are unchanged.
def _load_shared_error():
    for parent in Path(__file__).resolve().parents:
        for candidate in (parent / "shared_error.py",
                          parent / "batch" / "shared_error.py"):
            if candidate.is_file():
                try:
                    if str(candidate.parent) not in sys.path:
                        sys.path.insert(0, str(candidate.parent))
                    from shared_error import report_error
                    return report_error
                except Exception:
                    # A shared error program that is present but
                    # fails to load is treated the same as one
                    # that cannot be found: fall back, never
                    # raise at startup.
                    continue
    return None


_shared_report_error = _load_shared_error()


def _report_to_shared_error(step, error, kind="foreseen"):
    """Send one error to the one shared error program. Never raises."""
    if _shared_report_error is None:
        print(f"SHARED ERROR PROGRAM UNAVAILABLE — error not recorded: {error}",
              file=sys.stderr)
        return None
    try:
        return _shared_report_error(
            program=Path(__file__).name, step=step, error=error, kind=kind,
            error_type="FailedVerdict" if kind == "check_failed" else None)
    except Exception as exc:
        print(f"SHARED ERROR PROGRAM FAILED — error not recorded: {exc}",
              file=sys.stderr)
        return None


def _report_unknown(lines):
    """Report an UNKNOWN verdict to the one shared error program.

    UNKNOWN is the non-response case: the check ran, GitHub could
    not be read, and no answer came back. The report is marked as a
    non-response and carries the run's own detail -- the mark-
    published write failure when that is the road that ended
    UNKNOWN, otherwise the run's Reason line. MATCH and CHANGED
    are answers and never reach this helper.
    """
    detail = ""
    for line in reversed(lines):
        if line.startswith("Marked published: FAILED"):
            detail = line
            break
    if not detail:
        for line in reversed(lines):
            if line.startswith("Reason: "):
                detail = line[len("Reason: "):]
                break
    error = ("Non-response: the check could not read GitHub, "
             "so no answer came back")
    if detail:
        error = f"{error} — {detail}"
    _report_to_shared_error("verdict UNKNOWN", error, kind="check_failed")


def phoenix_today():
    return datetime.now(PHOENIX).date().isoformat()


def fetch_github_sha():
    """Return (full_sha, error_string). Exactly one is non-None.

    The read climbs a step-down ladder (2026-10-26, second form
    after the fresh-eyes review), and the ladder treats the ways
    the read can fail as different classes — the first form
    climbed the same ladder for all of them:

      CLIMBS the ladder (up to 3 tries; the allowed time stepping
      up — the standing TIMEOUT_SECONDS, then twice it, then four
      times it — with a wait before try 2 (5 seconds) and try 3
      (10 seconds)): failures where no complete answer arrived —
      a network error, a time-out, a cut or reset transfer, a
      server-error answer (5xx, and 408), and a non-JSON answer
      (an error page is not GitHub's answer to the question
      asked). Time and a fresh connection are the step-down: each
      try asks the same small question later, with longer to
      answer — the only "less" that exists for a one-record read.

      STOPS at once, with the reason named, UNKNOWN on the first
      answer (as the standing specification has it: these are
      answers GitHub already gave in full, and a larger time
      limit asks for nothing less because nothing is missing):
      a complete answer carrying an empty commit list; a complete
      answer carrying no commit sha; a "does not stand" answer
      (404); and a busy answer (429, or 403 — the unauthenticated
      API's rate-limit answer). For a busy answer the wait the
      server asks for is far beyond this check's budget, so the
      check does not spend it hitting the same limit again inside
      one run; the morning's own schedule runs the check again.

    When more than one try ran, the returned error carries EVERY
    try's reason in order ("try 1: …; try 2: …"), so an UNKNOWN
    names what actually happened first as well as last. That
    holds on the mixed path too: when a climbing failure is
    followed by a definitive answer, the error names the earlier
    tries first and the definitive answer last — a cut connection
    followed by a "does not stand" answer reads as both, not as
    the 404 alone. A definitive answer on the first try returns
    its bare reason, exactly as the one-read program gave it.
    A good publish is no longer reported UNKNOWN because a single
    read was cut short, and UNKNOWN is reached only after the
    ladder, or at once on a definitive answer.

    Time budget: the ladder's worst case is 15+5+30+10+60 = 120
    seconds, reached only when every try is a climbing failure.
    The callers — step 9 of the morning briefing job, which runs
    this check and, after a publish, the --mark-published run,
    and hand runs — name no time limit or kill for the step in
    their records, so nothing ends the check before the ladder
    and its verdict have run.
    """
    reasons = []
    for try_no, timeout in enumerate(
            (TIMEOUT_SECONDS, TIMEOUT_SECONDS * 2, TIMEOUT_SECONDS * 4),
            start=1):
        if try_no > 1:
            time.sleep(5 if try_no == 2 else 10)
        sha, error, may_retry = _fetch_github_sha_once(timeout)
        if sha is not None:
            return sha, None
        reasons.append(f"try {try_no}: {error}")
        if not may_retry:
            # A definitive answer stops the ladder at once. With
            # earlier tries behind it, the error carries their
            # reasons ahead of its own; on the first try it is the
            # bare reason, exactly as the one-read program gave.
            if len(reasons) > 1:
                return None, "; ".join(reasons)
            return None, error
    return None, "; ".join(reasons)


def _fetch_github_sha_once(timeout):
    """One read of the GitHub API at one time limit. Return
    (full_sha, error_string, may_retry): exactly one of the first
    two is non-None, and may_retry says whether the ladder may
    climb after this answer (see fetch_github_sha for the classes).

    Every exception is caught here -- network errors, HTTP errors, and
    read errors such as http.client.IncompleteRead (a truncated reply,
    which is neither an OSError nor a URLError) -- so a failed fetch
    always becomes UNKNOWN, never a traceback.
    """
    request = urllib.request.Request(
        API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "hearth-publish-check/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # An answer arrived. A server error (5xx) or a time-out
        # answer (408) may pass, so the ladder climbs; every other
        # client answer is definitive — busy (429, and 403, the
        # rate-limit answer on this unauthenticated endpoint),
        # "does not stand" (404), and the rest — and the ladder
        # does not climb.
        may_retry = exc.code == 408 or 500 <= exc.code <= 599
        return None, f"GitHub API request failed: {type(exc).__name__}: {exc}", may_retry
    except Exception as exc:
        return None, f"GitHub API request failed: {type(exc).__name__}: {exc}", True
    try:
        data = json.loads(body)
    except Exception as exc:
        return None, f"GitHub API returned non-JSON: {exc}", True
    if not isinstance(data, list) or not data:
        return None, "GitHub API returned no commits for that path", False
    first = data[0]
    sha = first.get("sha") if isinstance(first, dict) else None
    if not sha or not isinstance(sha, str):
        return None, "GitHub API response carried no commit sha", False
    return sha.strip(), None, False


def read_state_sha(state_file):
    """Return (sha_or_None, reason_or_None).

    The reason is the real one -- missing, empty, or unreadable with
    the underlying error -- and the caller prints it as-is.
    """
    try:
        text = state_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "no state on file"
    except Exception as exc:
        return None, f"state file unreadable: {type(exc).__name__}: {exc}"
    value = text.strip().splitlines()[0].strip() if text.strip() else ""
    if not value:
        return None, "no state on file (state file is empty)"
    return value, None


def state_value_problem(state_sha):
    """Return why a state value cannot be a valid SHA, or None if valid.

    A value shorter than 7 characters, or containing non-hex
    characters, is never allowed to match.
    """
    if len(state_sha) < MIN_STATE_SHA_LEN:
        return (
            f"state value '{state_sha}' is too short "
            f"({len(state_sha)} character(s), minimum {MIN_STATE_SHA_LEN}) "
            "to be a valid SHA"
        )
    bad = [c for c in state_sha if c not in HEX_DIGITS]
    if bad:
        return (
            f"state value '{state_sha}' contains non-hex character(s): "
            + ", ".join(repr(c) for c in bad)
        )
    return None


def shas_match(state_sha, github_sha):
    """A state value may be a short SHA; GitHub returns a full SHA.

    Match if the state value is a valid SHA prefix (at least
    MIN_STATE_SHA_LEN hex characters) and the full SHA starts with it,
    equivalently if the API SHA truncated to the state value's length
    equals it. Comparison is case-insensitive.
    """
    if not state_sha or not github_sha:
        return False
    if state_value_problem(state_sha) is not None:
        return False
    state = state_sha.strip().lower()
    github = github_sha.strip().lower()
    return github[: len(state)] == state


def write_state_atomic(state_file, sha):
    """Write sha into state_file atomically.

    The new value is written to a temp file in the same directory,
    flushed to disk, then os.replace() swaps it over the state file.
    A stop mid-write can only ever leave the whole old SHA or the
    whole new SHA in place, never an empty or partial file.
    """
    state_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(state_file.parent),
        prefix=state_file.name + ".",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(sha + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, state_file)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def compute(args, lines):
    """Do the check, appending detail lines. Return (verdict, exit_code)."""
    _rl("START", 1)
    state_sha, state_reason = read_state_sha(args.state_file)
    if state_sha:
        lines.append(f"State SHA: {state_sha}")
        _rl("OK", 1, f"state SHA on file: {state_sha}")
    else:
        lines.append("State SHA: (none)")
        _rl("OK", 1, f"state read: {state_reason or 'no state on file'}")

    _rl("START", 2)
    github_sha, error = fetch_github_sha()

    if error is not None:
        _rl("FAIL", 2, error)
        lines.append("GitHub SHA: (unavailable)")
        lines.append(f"Reason: {error}")
        return "UNKNOWN", 2

    lines.append(f"GitHub SHA: {github_sha}")
    _rl("OK", 2, f"GitHub SHA: {github_sha}")

    _rl("START", 3)
    if state_sha is None:
        # Preserve the real reason (missing / empty / unreadable).
        lines.append(f"Reason: {state_reason or 'no state on file'}")
        verdict = "CHANGED"
        _rl("OK", 3, f"verdict CHANGED — {state_reason or 'no state on file'}")
    else:
        problem = state_value_problem(state_sha)
        if problem is not None:
            lines.append(f"Reason: invalid state SHA - {problem}; treated as changed")
            verdict = "CHANGED"
            _rl("OK", 3, f"verdict CHANGED — invalid state SHA: {problem}")
        elif shas_match(state_sha, github_sha):
            lines.append("Reason: state SHA matches GitHub SHA")
            verdict = "MATCH"
            _rl("OK", 3, f"verdict MATCH — state SHA {state_sha} matches GitHub SHA {github_sha}")
        else:
            lines.append("Reason: GitHub SHA differs from state SHA")
            verdict = "CHANGED"
            _rl("OK", 3, f"verdict CHANGED — state SHA {state_sha} != GitHub SHA {github_sha}")

    if args.mark_published:
        _rl("START", 4)
        try:
            write_state_atomic(args.state_file, github_sha)
            lines.append(f"Marked published: state file updated to {github_sha}")
            _rl("OK", 4, f"state file updated to {github_sha}")
        except Exception as exc:
            lines.append(
                f"Marked published: FAILED - {type(exc).__name__}: {exc}"
            )
            _rl("FAIL", 4, f"state write failed: {type(exc).__name__}: {exc}")
            return "UNKNOWN", 2

    return verdict, 0


def emit(lines):
    """Print the full output to stdout and write the same to the dated log."""
    output = "\n".join(lines) + "\n"
    sys.stdout.write(output)
    sys.stdout.flush()
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{phoenix_today()}.log"
        # Append, so multiple runs on one day are each preserved in full.
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(output)
    except Exception as exc:
        print(f"Warning: could not write log: {exc}", file=sys.stderr)


def _main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check whether the Hearth prop inventory changed on GitHub."
    )
    parser.add_argument(
        "--mark-published",
        action="store_true",
        help="write the current full GitHub SHA into the state file "
        "(use only after a publish completes)",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help=f"state file path (default: {DEFAULT_STATE_FILE})",
    )
    args = parser.parse_args(argv)

    _rl_labels = {
        1: "read_state",
        2: "fetch_github_sha",
        3: "compare_shas",
    }
    if args.mark_published:
        _rl_labels[4] = "mark_published_write"
    _rl_begin("hearth", _rl_labels)

    lines = []
    lines.append("Hearth prop inventory publish check")
    lines.append(f"Date (America/Phoenix): {phoenix_today()}")
    lines.append(f"Repository: {REPO}")
    lines.append(f"Path: {FILE_PATH}")
    lines.append(f"State file: {args.state_file}")

    try:
        verdict, exit_code = compute(args, lines)
    except Exception as exc:
        # Last-resort guard: any unexpected error still produces a
        # verdict line, a log entry, and exit 2 -- never a bare
        # traceback with no verdict and no log.
        lines.append(f"Reason: unexpected error: {type(exc).__name__}: {exc}")
        verdict, exit_code = "UNKNOWN", 2

    lines.append(f"VERDICT: {verdict}")
    emit(lines)
    if verdict == "UNKNOWN":
        # A non-response is a problem (the admin's ruling, 2026-10-21):
        # report it to the shared error program so an error record
        # opens. The printed output above and the exit code (2)
        # are unchanged; the helper never raises.
        _report_unknown(lines)
    return exit_code


def main(argv=None):
    code = None
    try:
        code = _main(argv)
    finally:
        # UNKNOWN (exit 2) is this program's failure exit; MATCH and
        # CHANGED both exit 0 and both mean the check ran in full.
        _rl_finish(failed=(code != 0))
    return code


if __name__ == "__main__":
    sys.exit(main())
