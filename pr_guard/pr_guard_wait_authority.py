"""Wait-mode thread-authority orchestration for pr_guard."""

from __future__ import annotations

import subprocess
import time

from .pr_guard_reaction import (
    FINAL_SURVEY_BUDGET_SECS,
    probe_timeout_budget,
    wait_reaction,
)
from .pr_guard_threads import survey

__all__ = ["wait_with_thread_authority"]


def wait_with_thread_authority(
    pr: int, timeout_secs: int, accept_standing: bool
) -> int:
    try:
        preflight = survey(
            pr, reaction=False, timeout_secs=probe_timeout_budget(timeout_secs)
        )
    except subprocess.TimeoutExpired:
        print(
            "WAIT UNREADABLE (preflight): thread-authority survey timed out; "
            "no reaction probe was started"
        )
        return 1
    if any(t.classification == "DANGER" for t in preflight):
        print(
            "WAIT FINDINGS (pre-existing): unresolved findings at wait start "
            "— the review already ran; threads are the authority"
        )
        return 3
    deadline = time.monotonic() + timeout_secs
    if accept_standing:
        result = wait_reaction(pr, timeout_secs, True)
    else:
        result = wait_reaction(pr, timeout_secs)
    if result != 1:
        return result
    try:
        at_timeout = survey(
            pr,
            reaction=False,
            timeout_secs=FINAL_SURVEY_BUDGET_SECS,
        )
    except subprocess.TimeoutExpired:
        print("WAIT TIMEOUT: final survey UNREADABLE; retaining exit 1")
        return 1
    if any(t.classification == "DANGER" for t in at_timeout):
        print(
            "WAIT FINDINGS (at timeout): findings appeared during the wait; "
            "the reaction could not be attributed — threads are the authority"
        )
        return 3
    return 1
