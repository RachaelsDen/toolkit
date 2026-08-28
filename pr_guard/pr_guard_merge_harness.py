"""The shared fake-gh/fake-git/fake-clock harness for the merge-act
suites.

Thread 3832660856 (PR #40 round 4): the watch and round-3 suites used
to import the MergeGuardedTests TestCase itself to reuse this runner,
and unittest's loadTestsFromModule scans every module namespace for
TestCase subclasses regardless of where they were DEFINED — so the
eight merge tests ran three times under the aggregator's one-command
run (61 reported tests, 45 unique). The harness is therefore a PLAIN
class (and the fakes plain functions/constants): importing it into a
test module adds NOTHING to unittest discovery, and each suite runs
its own tests exactly once.

No network: every gh/git call, every fetch, and every sleep run on
the FakeClock (thread 3832522300) — the act's own sequencing is what
is under test.

PR #41 round 11: the well-known shas, argv constants, and record
builders moved to pr_guard_merge_fixtures.py (the harness stood at
247/250 pure LOC, HOT, and round 11 extends the fake git) and are
re-exported below so existing suite imports keep working. PR #41
round 25: the fake git moved ENTIRELY to pr_guard_merge_gitfake.py
(the round-25 two-case contract added the parent/base-tip probe
ANSWERS and the fork/range/marker diagnostic answers, and the harness
pressed its ceiling again); this module keeps the runner, the fake
gh, and the clock, wiring the git factory with every fixture knob
its branch closed over. PR #41 round 31 (thread 3835587497): the
fake GH moved the same way to pr_guard_merge_ghfake.py (the harness
stood at 265 pure LOC, over the ceiling since the round-25 recount)
and the clock now also patches pr_guard_settle_watch (the settling
watch's round-31 split home — its sleeps would run REAL otherwise).
Like the fixtures, both fakes are PLAIN modules: importing them adds
nothing to unittest discovery.
"""

import contextlib
import io
import os
import subprocess
from contextlib import redirect_stdout
from unittest import mock

from . import pr_guard_common
from . import pr_guard_completion
from . import pr_guard_merge
from . import pr_guard_quiet
from . import pr_guard_settle
from . import pr_guard_settle_watch
from .pr_guard_merge_fixtures import (
    BASE_TIP,
    CANONICAL_REMOTE_V,
)
from .pr_guard_merge_fixtures import GUARD_ID
from .pr_guard_merge_fixtures import GUARD_NO_SIGN
from .pr_guard_merge_fixtures import FakeClock, HEAD, MERGE_ARGV, MERGE_SHA
from .pr_guard_merge_fixtures import SNAPSHOT_ARGV
from .pr_guard_merge_fixtures import (
    FORK_SHA,
    FOREIGN_PARENT,
    LANDING_PARENT,
    PR_HEAD_REF,
)
from .pr_guard_merge_fixtures import PR_NODE_ID, REST_PR_ARGV
from .pr_guard_merge_fixtures import REVERT_HEAD, POLL_ARGV, REPO_FLAG
from .pr_guard_merge_fixtures import REVERT_PR_URL, WORKTREE_TMP
from .pr_guard_merge_gitfake import make_git_fake
from .pr_guard_merge_ghfake import make_gh_fake
from .pr_guard_merge_fixtures import rc_sequence
from .pr_guard_merge_fixtures import HEAD_ARGV, GRAPHQL_ARGV
from .pr_guard_merge_fixtures import DEQUEUE_ARGV, NODE_ID_ARGV
from .pr_guard_merge_fixtures import merged, pending, queued_entry
from .pr_guard_merge_fixtures import landing_probes
from .pr_guard_merge_fixtures import revert_argv, thread
from .pr_guard_rulesets_test import gate_ruleset

__all__ = [
    "BASE_TIP", "CANONICAL_REMOTE_V", "DEQUEUE_ARGV", "FakeClock",
    "FORK_SHA",     "FOREIGN_PARENT", "GRAPHQL_ARGV", "GUARD_ID", "GUARD_NO_SIGN", "HEAD", "HEAD_ARGV",
    "LANDING_PARENT", "MERGE_ARGV", "MERGE_SHA", "NODE_ID_ARGV",
    "POLL_ARGV", "PR_HEAD_REF", "PR_NODE_ID", "REST_PR_ARGV",
    "REPO_FLAG", "REVERT_HEAD", "REVERT_PR_URL", "SNAPSHOT_ARGV",
    "WORKTREE_TMP", "MergeHarness", "landing_probes", "merged",
    "pending", "queued_entry", "revert_argv", "thread",
]


class MergeHarness:
    """Runs pr_guard_merge.merge_guarded against fakes and records the
    argv sequence, survey events, and survey times. A deliberately
    NON-TestCase class (thread 3832660856): importing it never adds
    discovered tests. After a run, .clock and .survey_times expose the
    fake clock and per-survey monotonic timestamps for assertions.

    Thread 3833073940 (PR #41): queue_entries drives the GraphQL
    mergeQueueEntry probe — each item is None (ABSENT), a dict like
    {"state": "QUEUED"} (QUEUED), or "FAIL" (probe unreadable, which
    triggers the REST mergeable_state corroboration read; rest_states
    drives that, defaulting to "blocked"). The last provided entry
    repeats forever. Thread 3833073949: merge_rc forces the gh pr
    merge dispatch exit code. Thread 3833073952: gh_repo injects
    GH_REPO into the environment for the startup-warning tests.
    """

    def run_guarded(
        self,
        surveys,
        pr_reads,
        poll_states=None,
        rc_for=None,
        cancel_reads=None,
        # Thread 3832522300: round-1 sequencing scenarios pin the
        # window to the single PR #39 snapshot; window/deadline
        # semantics live in the watch and round-3 suites.
        quiet_secs=0,
        head_reads=None,
        base="dev",
        clock_cls=FakeClock,
        queue_entries=None,
        rest_states=None,
        merge_rc=None,
        gh_repo=None,
        # Thread 3833540921: the landed-commit parent probe's exit
        # code — 0 (default) makes the landing a two-parent merge
        # commit (git revert -m 1); nonzero makes it single-parent
        # (plain git revert, the merge-queue squash/rebase shape).
        parent_probe_rc=0,
        # Thread 3833671111 (PR #41 round 9), reworked by thread
        # 3834883632 (round 21): the PR's commit list (oldest-first
        # oids) served to the PAGINATED REST commit read
        # (repos/.../pulls/<n>/commits?per_page=100&page=<k>) —
        # None defaults to the single-commit squash shape, so the
        # single-parent revert stays a plain revert of MERGE_SHA; a
        # multi-commit list selects the rebased-RANGE shape, and a
        # >100-oid list spans TWO pages (the fixture cuts the chunks).
        # range_probe_rc drives the `<oldest>^` availability probe
        # (nonzero = pre-range commit unavailable → per-commit
        # fallback).
        pr_commits=None,
        range_probe_rc=0,
        # Thread 3833671126 (PR #41 round 9): an exception raised by
        # the merge DISPATCH itself (Ctrl-C / subprocess error while
        # gh pr merge is returning) — the reconcile-then-re-raise path.
        merge_exc=None,
        # Thread 3836217633 (PR #45 round 10, P1): the dispatch
        # exits 0 WITH gh's already-merged no-op signature in its
        # stderr ("... was already merged") — the idempotent no-op
        # success the round-10 classification must treat as the
        # FAILED-dispatch class for attribution.
        merge_noop=False,
        # Thread 3833762325 (PR #41 round 10): the `git remote -v`
        # listing served to the canonical-remote resolution — the
        # default is the ordinary canonical checkout (origin);
        # fork-checkout scenarios list a fork origin (plus or minus a
        # canonical upstream).
        remote_v=CANONICAL_REMOTE_V,
        # Thread 3833762316 (PR #41 round 10): per-rev exit codes for
        # the `git rev-parse --verify` probes — a callable on the rev
        # string, overriding the parent/range probe defaults so a
        # fixture can make objects unavailable BEFORE a fetch and
        # available after it (or never).
        rev_rc_for=None,
        # Thread 3833880596 (PR #41 round 11), widened by thread
        # 3834210484 (round 14): a callable consulted BEFORE the
        # built-in git handlers — returning (rc, stdout) answers that
        # argv, None defers to the defaults. It receives the argv AND
        # the STDIN text of the call (input= kwarg): this is how the
        # fork-point probe gets its stdout sha (see
        # pr_guard_merge_fixtures.landing_probes) and how the piped
        # rev-list --stdin / diff-tree --stdin / patch-id --stable
        # stages of the patch-id discriminator are served by their
        # INPUT rather than their argv.
        git_answers=None,
        # Thread 3834375737 (PR #41 round 15): the dequeuePullRequest
        # mutation's exit code — the default (1) keeps the watch-only
        # fallback shapes of the earlier rounds' fixtures (the mutation
        # cannot remove the entry), and 0 serves the accepted payload
        # so a fixture can converge through the dequeue. Thread
        # 3834590319 (round 17): a LIST serves per-ATTEMPT codes (last
        # repeats) so the retry scenarios can fail-then-succeed.
        dequeue_rc=1,
        # Thread 3834400946 (PR #41 round 16): gh_host injects GH_HOST
        # into the environment for the startup-block tests; after a
        # run, .gh_envs lists the env dict every dispatched gh command
        # carried (each must pin GH_HOST=github.com).
        gh_host=None,
        # Thread 3834400954 (PR #41 round 16): remote_heads maps branch
        # name -> the sha `git ls-remote` reports for refs/heads/<name>
        # (absent branches report nothing); revert_head is the sha the
        # fake worktree reports for `git -C <tmp> rev-parse HEAD`.
        remote_heads=None,
        revert_head=REVERT_HEAD,
        # Thread 3835145981/3835175506/08 (PR #41 round 25): the
        # two-case contract's probe ANSWERS — landing_parent answers
        # `git rev-parse --verify <MERGE_SHA>^` and base_tip answers
        # `git rev-parse --verify <remote>/<base>`; the DEFAULTS are
        # EQUAL (the automated single-parent shape: parent IS the
        # current base tip), and a fail-closed fixture passes a
        # DIFFERENT landing_parent (or an unequal base_tip).
        landing_parent=LANDING_PARENT,
        base_tip=BASE_TIP,
    ):
        out = io.StringIO()
        events: list[tuple] = []
        survey_times: list[float] = []
        survey_reactions: list[bool] = []
        clock = clock_cls()
        self.raised: BaseException | None = None
        self.revert_tmp = WORKTREE_TMP
        dequeue_next = rc_sequence(dequeue_rc)
        # Round 25 split: the fake-git branch of fake_run lives in
        # pr_guard_merge_gitfake (the harness pressed its 250
        # pure-LOC ceiling with the round-25 probe answers);
        # state["tmp"] carries the worktree-add capture back here.
        # Round 31 split: the fake-GH branch lives in
        # pr_guard_merge_ghfake the same way (the harness was over
        # the ceiling at 265).
        git_state = {"tmp": WORKTREE_TMP}
        git_fake = make_git_fake(
            git_answers, base, landing_parent, base_tip,
            parent_probe_rc, range_probe_rc, rev_rc_for, remote_v,
            revert_head, remote_heads, git_state,
        )
        gh_fake = make_gh_fake(
            cancel_reads, head_reads, HEAD, poll_states, merged(base),
            pr_commits, queue_entries, rest_states, dequeue_next,
        )

        def fake_survey(pr, reaction=True):
            events.append(("survey",))
            survey_times.append(clock.monotonic())
            survey_reactions.append(reaction)
            item = next(surveys)
            if isinstance(item, BaseException):
                raise item
            return item

        def fake_run(argv, **kwargs):
            events.append(("run", tuple(argv), kwargs.get("env")))
            if argv[:1] == ["git"]:
                handled = git_fake(argv, kwargs.get("input"))
                if handled is not None:
                    return handled
            handled = gh_fake(argv)
            if handled is not None:
                return handled
            rc = 0
            if (
                argv[:3] == ["gh", "pr", "merge"]
                and "--disable-auto" not in argv
            ):
                # Thread 3833671126: the dispatch itself raising (Ctrl-C
                # / subprocess error) before any return code exists.
                if merge_exc is not None:
                    raise merge_exc
                if merge_rc is not None:
                    rc = merge_rc
                # Thread 3836217633 (PR #45 round 10): gh's
                # already-merged no-op success — rc 0 with the
                # signature on stderr, the shape the round-10
                # classification must demote to the ambiguous class.
                if merge_noop:
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        stdout="",
                        stderr=(
                            "! Pull request #39 was already merged"
                            "\n"
                        ),
                    )
            elif rc_for:
                rc = rc_for(argv)
            stdout = REVERT_PR_URL if argv[:3] == ["gh", "pr", "create"] else ""
            return subprocess.CompletedProcess(
                argv, rc, stdout=stdout, stderr="boom" if rc else ""
            )

        patchers = [
            mock.patch.object(pr_guard_merge, "gh_rest_pr", side_effect=lambda pr: next(pr_reads)),
            mock.patch.object(pr_guard_merge, "fetch_gate_rulesets", return_value=[gate_ruleset()]),
            mock.patch.object(pr_guard_merge, "default_branch", return_value="main"),
            mock.patch.object(pr_guard_merge, "survey",
                              side_effect=fake_survey),
            mock.patch.object(pr_guard_merge.subprocess, "run",
                              side_effect=fake_run),
            mock.patch.object(pr_guard_merge, "time", clock),
            # Thread 3836217630/3836217633 (PR #45 round 10): the
            # quiet-period watch split to pr_guard_quiet (the 250
            # pure-LOC ceiling — merge stood at 247 with the no-op
            # classification inbound) — patch ITS survey and time
            # too, or the watch would call the real survey and read
            # the real clock.
            mock.patch.object(pr_guard_quiet, "time", clock),
            mock.patch.object(pr_guard_quiet, "survey",
                              side_effect=fake_survey),
            # Thread 3833251667 (PR #41 round 6): the cancel/queue
            # sleeps moved to pr_guard_completion (pr_guard_revert no
            # longer imports time) — patch the new home or the tests
            # would really sleep.
            mock.patch.object(pr_guard_completion, "time", clock),
            # Thread 3833540913 (PR #41 round 8): the queue-settlement
            # sleeps (watch cadence + deadline arithmetic) moved again,
            # into pr_guard_settle — same reason, patch the new home.
            mock.patch.object(pr_guard_settle, "time", clock),
            # Thread 3835587497 (PR #41 round 31): the settling watch
            # itself moved to pr_guard_settle_watch (the pacing fix's
            # split-FIRST home) — patch ITS time too or the watch's
            # pacing and cadence sleeps would run on the REAL clock.
            mock.patch.object(pr_guard_settle_watch, "time", clock),
            # Thread 3834093639 (PR #41 round 13): the shared
            # deadline_clamped_sleep reads time.monotonic through
            # pr_guard_common (the quiet/settle/queue watches all
            # funnel their clamped sleeps through it now) — patch that
            # home too or the helper would read the REAL clock while
            # FakeClock.sleep advances fake seconds.
            mock.patch.object(pr_guard_common, "time", clock),
        ]
        env_overrides = {
            key: value
            for key, value in (("GH_REPO", gh_repo), ("GH_HOST", gh_host))
            if value is not None
        }
        env_ctx = (mock.patch.dict(os.environ, env_overrides) if env_overrides else contextlib.nullcontext())
        try:
            for patcher in patchers:
                patcher.start()
            with env_ctx, redirect_stdout(out):
                code = pr_guard_merge.merge_guarded(
                    39, HEAD, base, quiet_secs
                )
        except BaseException as exc:
            # Thread 3833360219 (PR #41 round 7): the interrupt
            # reconciliation re-raises AFTER the cancel path — record
            # the exception (code None == the act exited by exception,
            # i.e. nonzero) and keep the captured output/argv for the
            # assertions.
            self.raised = exc
            code = None
        finally:
            for patcher in patchers:
                patcher.stop()
        self.revert_tmp = git_state["tmp"]
        argvs = [" ".join(ev[1]) for ev in events if ev[0] == "run"]
        self.clock = clock
        self.survey_times = survey_times
        self.survey_reactions = survey_reactions
        self.gh_envs = [ev[2] for ev in events if ev[0] == "run" and ev[1][:1] == ("gh",)]
        return code, out.getvalue(), argvs, events

    def revert_tail(self, argvs: list[str]) -> list[str]:
        """The argv AFTER the final completion poll — the revert steps."""
        last_poll = len(argvs) - 1 - argvs[::-1].index(POLL_ARGV)
        return argvs[last_poll + 1 :]

    def revert_create_argv(self, argvs: list[str]) -> str:
        """The full `gh pr create` argv of the revert PR, title and
        body included — thread 3833360211's truthful-copy assertions
        read the copy the PR would actually carry."""
        for argv in argvs:
            if argv.startswith("gh pr create"):
                return argv
        return ""
