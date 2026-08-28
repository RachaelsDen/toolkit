"""pr_guard merge-act round-35 tests (PR #45 round 3).

Thread 3835846317 (P2) — the merge-tip reuse probe FAILS CLOSED:
`git rev-parse FETCH_HEAD^2` exits nonzero for the missing second
parent AND for transient git failures alike, so the rc==0 boolean
read an ERRORED probe as "not a merge" and reuse proceeded over an
unproven tip. The probe is now a TRI-STATE — rc 0 = merge, the
LEGITIMATE missing-parent shape = PROVEN single-parent, anything
else = UNREADABLE — and only the PROVEN single-parent tip is
reusable; a transient-failure fixture must take the SUFFIX path.
(Refit at PR #45 round 4, thread 3835877368: the legitimate shape
is the QUIET --verify probe's rc 1 — exit-code-only, locale cannot
move it — so the wrong-rc fixture uses rc 2, a code real git never
produces for this probe.)

Thread 3835846318 (P1) — preserve identity for ambiguous FAILED
dispatches: a stale-OPEN pre-dispatch record on an already-landed
PR makes the merge command fail, and the discarded open-record sha
left the reconcile with NO evidence — the mismatch/DANGER cycle
(automatic revert) could run against a historical merge this
invocation never dispatched. The kept open-record sha, the
dispatch-time wall clock, and the landing's COMMITTER DATE
(`git log -1 --format=%ct` through the canonical remote) now gate
the reconciliation. (Repinned at PR #45 round 7, thread
3836043653: a committer date BEFORE the dispatch is AMBIGUOUS, not
pre-existing — no fixed skew margin bounds the local/GitHub clock
divergence, so the by-date pre-existing verdict is RETIRED; only a
FRESH date (clearly AFTER the dispatch, UNEQUAL sha) runs the
ordinary post-merge path — including its revert. Repinned again at
PR #45 round 8, thread 3836092104: NO date runs the ordinary path
anymore — a GitHub clock ahead of the runner's FUTURE-DATES
historical merges, so the fresh attribution is the OBSERVED
TRANSITION alone; the fresh-landing test polls OPEN first and
asserts %ct is never consulted.)

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; the git_answers fixtures serve the ^2 probe's transient
failures (3-tuple answers carry stderr) and the identity gate's
committer-date read (ct on either side of the fixtures' WALL_NOW
dispatch clock; None = unreadable).

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round35_test -v
"""

import unittest

from .pr_guard_merge_fixtures import WALL_NOW
from .pr_guard_merge_harness import (
    HEAD,
    MERGE_SHA,
    MergeHarness,
    merged,
    pending,
    thread,
)

RUNNER = MergeHarness()
BRANCH = f"revert/pr39-{MERGE_SHA[:7]}"
PUSHED_HEAD = "c0ffee0000000000000000000000000000000f00"
OLD_REVERT = "0dda1f0000000000000000000000000000000000"
LOCAL_DIFF = (
    "diff --git a/src/server/gate.ts b/src/server/gate.ts\n"
    "--- a/src/server/gate.ts\n"
    "+++ b/src/server/gate.ts\n"
    "@@ -1,2 +1,1 @@\n"
    "-import { gate } from \"./gate\"\n"
    "-import { old } from \"./old\"\n"
)
PIDS = {
    LOCAL_DIFF.strip(): "111100000000000000000000000000000000aaaa",
}


def pinned():
    return iter([{"head": {"sha": HEAD}, "base": {"ref": "dev"}}])


def open_record(merge_commit_sha: str = ""):
    # Thread 3835846318: the STALE-OPEN pre-dispatch REST shape —
    # state "open", merged=false, and (optionally) the merge_commit_
    # sha GitHub's separately cached PR state can still expose for a
    # PR that has already landed.
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


# Thread 3835846317: the patch-id stages of the round-33/34 fixtures
# with a CONTROLLABLE FETCH_HEAD^2 answer — parent2 is the Completed
# (rc, stdout, stderr) the QUIET --verify probe receives:
# (0, sha, "") = a merge; (1, "", "") = proven single-parent (the
# real quiet form's exit code, thread 3835877368's rc-only rule; the
# reuse path the round-34 suite pins); anything else = the transient
# failures under test here.
def parent2_answers(parent2: tuple):
    fetched: list[bool] = []

    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "fetch"]:
            fetched.append(True)
            return (0, "")
        if g[:2] == ["git", "diff"]:
            return (0, LOCAL_DIFF)
        if g[:2] == ["git", "patch-id"]:
            pid = PIDS.get((stdin or "").strip())
            if pid is None:
                return None
            return (0, f"{pid} 0000000000000000000000000000000000000000\n")
        if (
            g[:2] == ["git", "rev-parse"]
            and g[2:] == ["--verify", "--quiet", "FETCH_HEAD^2"]
        ):
            return parent2 if fetched else None
        return None

    return answers


# Thread 3835846318: the identity gate's date evidence — ct serves
# `git log -1 --format=%ct <merge_sha>` (None = the probe fails);
# every other git argv falls through to the harness defaults.
def date_answers(ct: int | None):
    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "log"] and "--format=%ct" in g:
            if ct is None:
                return (1, "")
            return (0, f"{ct}\n")
        return None

    return answers


class TransientMergeProbeTests(unittest.TestCase):
    def test_transient_stderr_parent2_probe_fails_closed_to_suffix(
        self,
    ):
        # Given: the occupied candidate signatures EXACTLY like the
        # legitimate earlier-retry branch — sha differs, patch-id
        # matches, and the tip's FIRST parent is the base — but the
        # FETCH_HEAD^2 probe FAILS TRANSIENTLY: rc 128 with a stderr
        # that real git's QUIET probe never prints (thread 3835846317:
        # the rc alone cannot tell "no parent two" from "git broke",
        # and thread 3835877368's rc-only rule still reads 128 as a
        # fatal, not the quiet form's legitimate rc 1).
        surveys = iter([[thread("11", "resolved")]])

        # When: the probe answers a transient git failure's stderr.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=parent2_answers(
                (
                    128,
                    "",
                    "fatal: unable to read sha1 file: No such file "
                    "or directory",
                )
            ),
        )

        # Then: NOT reused — an unproven tip never carries the urgent
        # PR — the suffix push runs and the PR opens against -2; the
        # probe itself ran and the ancestry probe stayed UNREACHED
        # (the fail-closed rejection precedes it).
        self.assertEqual(code, 1)
        self.assertNotIn("REVERT BRANCH REUSED", out)
        self.assertIn("REVERT BRANCH SUFFIXED", out)
        self.assertIn("3835846317", out)
        tmp = RUNNER.revert_tmp
        self.assertIn(
            f"git -C {tmp} rev-parse --verify --quiet FETCH_HEAD^2",
            argvs,
        )
        self.assertNotIn(f"git -C {tmp} rev-parse FETCH_HEAD^", argvs)
        self.assertIn(
            f"git -C {tmp} push origin HEAD:refs/heads/{BRANCH}-2",
            argvs,
        )
        create = RUNNER.revert_create_argv(argvs)
        self.assertIn(f"--head {BRANCH}-2", create)
        self.assertIn("REVERT PR OPENED", out)

    def test_wrong_rc_parent2_probe_fails_closed_to_suffix(self):
        # Given: the same matching-content, matching-first-parent
        # candidate, with the FETCH_HEAD^2 probe exiting a code real
        # git never produces for the missing parent (rc 2 — the
        # quiet form's legitimate missing-parent exit is EXACTLY 1,
        # so 2 can only be a broken probe; refit at round 4 because
        # thread 3835877368's rc-only rule made rc 1 the PROVEN
        # single-parent verdict this fixture used to serve).
        surveys = iter([[thread("11", "resolved")]])

        # When: the probe answers the wrong exit code.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            pinned(),
            poll_states=[merged(head=PUSHED_HEAD)],
            remote_heads={BRANCH: OLD_REVERT},
            git_answers=parent2_answers((2, "", "")),
        )

        # Then: the suffix path again — only rc 1 (with rc 0 the
        # merge shape) decides; every other rc is unreadable.
        self.assertEqual(code, 1)
        self.assertNotIn("REVERT BRANCH REUSED", out)
        self.assertIn("REVERT BRANCH SUFFIXED", out)
        self.assertIn(
            f"git -C {RUNNER.revert_tmp} push origin "
            f"HEAD:refs/heads/{BRANCH}-2",
            argvs,
        )
        self.assertIn("REVERT PR OPENED", out)


class FailedDispatchIdentityTests(unittest.TestCase):
    def test_stale_open_landing_sha_match_banners_ambiguous(self):
        # Given: the pre-dispatch REST record is STALE-OPEN on an
        # already-landed PR (thread 3835846318's consistency window)
        # and still exposes the landing's sha as merge_commit_sha —
        # round 2 discarded that value, leaving the failed dispatch's
        # reconcile with NO identity evidence at all. Repinned at
        # round 5 (thread 3835944058) for the margin-clearing date
        # upgrade, and again at round 6 (thread 3836003345): the
        # upgrade is GONE — the equal object may be the AGED
        # SYNTHETIC a fresh landing REUSED, and the reused object
        # carries its OLD test-merge date, so the date cannot
        # arbitrate and equal OPEN SHAs are ALWAYS ambiguous.
        surveys = iter([[thread("11", "resolved")]])

        # When: the merge command fails ("already merged"), the
        # reconcile poll observes the landing, its sha EQUALS the
        # kept open-record sha, and its committer date predates the
        # dispatch-time wall clock by 1000s (well past the 300s
        # margin — which no longer matters on this arm).
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record(MERGE_SHA)]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 1000),
        )

        # Then: the uniform AMBIGUOUS disposition — repinned at
        # round 17 (thread 3836600782): the equality and the date
        # are banner REPORTS only (the committer-date probe is
        # deleted with the attribution arms), so the banner cites
        # the chain and demands the manual check: exit 1, NO
        # pre-existing verdict, NO revert, NO quiet watch (exactly
        # the closing survey), and NO date read runs at all.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertIn("3835944058", out)
        self.assertIn("3836003345", out)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("QUIET PERIOD", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_stale_open_old_committer_date_banners_ambiguous(self):
        # Given: the stale-OPEN record carried NO sha — the only
        # remaining evidence is the landing's COMMITTER DATE, and it
        # predates the dispatch-time wall clock by 1000s (beyond
        # round 5's 300s margin). Repinned at round 7 (thread
        # 3836043653): the runner clock and GitHub's commit clock are
        # UNSYNCHRONIZED, and a runner >= that far AHEAD of GitHub's
        # makes a FRESH merge read before-dispatch by more than any
        # fixed margin — so the margin never separated fresh from
        # pre-existing and the by-date pre-existing verdict is gone.
        surveys = iter([[thread("11", "resolved")]])

        # When: the failed dispatch reconciles into the MERGED
        # observation and the date probe answers a ct 1000s BEFORE
        # the fake clock's WALL_NOW dispatch timestamp.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("")]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 1000),
        )

        # Then: the uniform AMBIGUOUS manual-check banner — no
        # mismatch assertions, no quiet watch, NO automatic revert,
        # exit 1 — and (repinned at round 17, thread 3836600782) NO
        # evidence read runs at all: the date probe is deleted with
        # the attribution arms it fed.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836043653", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertNotIn("QUIET PERIOD", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_fresh_landing_after_failed_dispatch_banners_ambiguous(
        self,
    ):
        # Given: the dispatch failed only because the connection died
        # AFTER GitHub accepted the request (thread 3833073949's
        # unknown outcome) — repinned at round 8 (thread 3836092104):
        # the fresh attribution is the OBSERVED TRANSITION (never a
        # committer date); repinned again at round 9 (thread
        # 3836149500): the crediting OPEN read is POST-BASELINE;
        # repinned once more at round 10 (thread 3836217630): the
        # baseline is the first LIVE read (>= one real poll interval
        # past the dispatch), so the still-OPEN reads span THREE
        # polls before the fourth observes the landing.
        surveys = iter(
            [[thread("11", "resolved")], [thread("21", "DANGER")]]
        )

        # When: the reconcile poll reads the still-OPEN PR on the
        # pre-interval, live-baseline, and crediting polls before
        # the landing — a committer date 3600s BEFORE the dispatch
        # would have banner'd ambiguous on any date arm, and the
        # quiet watch's first survey finds a DANGER thread.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("")]),
            poll_states=[pending(), pending(), pending(), merged()],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) - 3600),
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # observed transition attributes NOTHING (the chain proved
        # every between-reads signal reproducible by ordered cache
        # snapshots of one historical timeline), so even this
        # genuinely-fresh landing reports the uniform AMBIGUOUS
        # manual banner: NO assertions, NO quiet watch, NO revert —
        # a human attributes it against the server timeline.
        self.assertEqual(code, 1)
        self.assertNotIn("PRE-EXISTING MERGE", out)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("POST-MERGE DANGER", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("MERGED CLEAN:", out)

    def test_unreadable_committer_date_is_ambiguous_manual_banner(self):
        # Given: the stale-OPEN record carried no sha AND the date
        # evidence is UNREADABLE — the %ct probe itself fails (no
        # canonical remote, a failed sha fetch, or a failed probe
        # all collapse to the same shape here).
        surveys = iter([[thread("11", "resolved")]])

        # When: the failed dispatch reconciles into a MERGED
        # observation the evidence cannot attribute.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("")]),
            poll_states=[merged()],
            merge_rc=1,
            git_answers=date_answers(ct=None),
        )

        # Then: the uniform AMBIGUOUS banner (every failed-dispatch
        # landing is one disposition now, thread 3836600782) — a
        # PRE-EXISTING-style manual check, NO automatic revert, exit
        # 1, never MERGED CLEAN; the unreadable-date scenario is
        # indistinguishable because NO date read runs at all.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("--format=%ct", " ".join(argvs))
        self.assertNotIn("QUIET PERIOD", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


if __name__ == "__main__":
    unittest.main()
