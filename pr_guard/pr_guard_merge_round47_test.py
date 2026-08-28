"""pr_guard merge-act round-47 tests (PR #45 rounds 15-16).

Thread 3836501981 (round 15, P1) revised by thread 3836565818
(round 16, P1) — keep paced cached OPEN reads ambiguous by
SAME-CLOCK evidence only: a stale pre-dispatch OPEN response for
an already-merged PR can persist for at least TWO poll intervals
(the first paced response arming the baseline, the second setting
observed=True) before the cache refreshes to the historical
MERGED; elapsed LOCAL time does not prove the two reads came from
distinct SERVER state or bound GitHub's cache staleness. The fix:
the transition evidence holder records the PR record's `updatedAt`
on every read, and the FRESH attribution (holder.attributed(),
what the identity gate's transition arm consumes) requires the
LANDING read's stamp to have ADVANCED past the BASELINE read's
own — two stamps the SERVER authored and this invocation's own
reads recorded, so the comparison never crosses clock domains
(thread 3836565818's same-clock principle): advancement between
two reads we ourselves performed proves the record changed
server-side during our watch, while a frozen/partial cache serves
stamps that do NOT advance between our reads. Round 15 compared
the landing stamp against the LOCAL dispatch_ts as well — a
cross-clock clause with no sound discrimination: a runner clock
BEHIND GitHub's puts a HISTORICAL merge's server-authored stamp
past the local dispatch moment, so the clause passed exactly the
merges it existed to refuse — retired in round 16 (dispatch_ts
stays in the holder for the identity gate's committer-date
REPORTING only). Anything but advancement between our reads — a
static stamp (one frozen snapshot, even one stamped past the
dispatch), a missing/unparseable stamp — fails closed to AMBIGUOUS.

PR #45 round 17 (thread 3836600782, P1 — the TERMINAL resolution):
the transition/corroboration machinery this suite's scenarios
exercised is RETIRED — the reviewer's rounds 7-17 chain proved
every between-reads attribution signal reproducible by ordered
cache snapshots of one historical timeline — so every
failed-dispatch landing below now pins the UNIFORM AMBIGUOUS
disposition (manual banner, NO revert), and the state-machine /
corroboration unit tests are deleted with the machinery.

No network: the shared fake-gh/fake-git/fake-clock harness drives
the act; date_answers serves the %ct reads. The window records are
LOCAL to this file (updatedAt included) so the suite pins the
corroboration rule end-to-end at exact fake seconds.

Run: cd .omo/start-work && python3 -m unittest pr_guard_merge_round47_test -v
"""

import unittest
from .pr_guard_merge_fixtures import HEAD, MERGE_SHA, WALL_NOW, iso_at
from .pr_guard_merge_harness import FakeClock, MergeHarness, thread

RUNNER = MergeHarness()
# The reviewer's stale-cache stamps: the frozen pre-merge record
# (an hour before the dispatch), the historical merge's record
# still before the LOCAL dispatch moment — and thread 3836565818's
# behind-clock shape, the historical merge's server-authored stamp
# EXCEEDING the local dispatch_ts (the runner clock sits behind
# GitHub's) while the frozen/partial cache serves that one stamp
# on BOTH our reads — plus the static and the corroborating
# post-dispatch variants.
STALE_AT = iso_at(-3600.0)
HISTORICAL_AT = iso_at(-1800.0)
BEHIND_CLOCK_AT = iso_at(3600.0)
STATIC_AT = iso_at(60.0)
FRESH_AT = iso_at(60.0)


def open_landed(updated_at: str) -> dict:
    return {
        "state": "OPEN",
        "mergeCommit": None,
        "baseRefName": "dev",
        "headRefOid": HEAD,
        "updatedAt": updated_at,
    }


def merged_landed(updated_at: str) -> dict:
    return {
        "state": "MERGED",
        "mergeCommit": {"oid": MERGE_SHA},
        "baseRefName": "dev",
        "headRefOid": HEAD,
        "updatedAt": updated_at,
    }


def open_record(merge_commit_sha: str = ""):
    return {
        "head": {"sha": HEAD},
        "base": {"ref": "dev"},
        "state": "open",
        "merged": False,
        "merge_commit_sha": merge_commit_sha,
    }


def date_answers(ct: int | None):
    def answers(argv, stdin):
        g = ["git", *argv[3:]] if argv[1:2] == ["-C"] else argv
        if g[:2] == ["git", "log"] and "--format=%ct" in g:
            if ct is None:
                return (1, "")
            return (0, f"{ct}\n")
        return None

    return answers


class PacedCacheWindowTests(unittest.TestCase):
    def test_behind_clock_frozen_historical_window_stays_ambiguous(self):
        # Given: thread 3836565818's exact scenario — a failed
        # dispatch (merge_rc=1) on an already-merged PR whose
        # frozen/partial cache serves the HISTORICAL merge's own
        # record through the whole window: the poll reads OPEN at
        # 0s (unspaced), OPEN at 10s (ARMS the live baseline), OPEN
        # at 20s (CREDITS the transition, thread 3836437095's
        # spacing), and MERGED at 30s — every read carrying the
        # SAME updatedAt, a stamp the runner clock BEHIND GitHub's
        # puts PAST the local dispatch moment (round 15's
        # landing > dispatch_ts clause is satisfied by it), with a
        # future-dated committer timestamp for the date-reporting
        # arm.
        surveys = iter([[thread("11", "resolved")]])

        # When: the paced-but-uncorroborated window lands.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[
                open_landed(BEHIND_CLOCK_AT),
                open_landed(BEHIND_CLOCK_AT),
                open_landed(BEHIND_CLOCK_AT),
                merged_landed(BEHIND_CLOCK_AT),
            ],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17 — the stamp corroboration this test pinned is
        # part of the retired machinery; the disposition is uniform
        # now): manual banner, NO revert plumbing, NO clean-path
        # cycle; exit 1.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836565818", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("LANDED DURING CANCELLATION", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertNotIn("gh pr create", " ".join(argvs))
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_static_stamp_across_the_window_stays_ambiguous(self):
        # Given: the static shape — every read (the paced OPENs
        # AND the MERGED landing) carries the SAME updatedAt, one
        # stamped even AFTER the dispatch: a frozen record never
        # proves a server-side change, whatever its stamp says.
        surveys = iter([[thread("11", "resolved")]])

        # When: the window lands on the frozen stamp.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[
                open_landed(STATIC_AT),
                open_landed(STATIC_AT),
                open_landed(STATIC_AT),
                merged_landed(STATIC_AT),
            ],
            merge_rc=1,
            git_answers=date_answers(ct=int(WALL_NOW) + 3600),
        )

        # Then: the uniform AMBIGUOUS banner (thread 3836600782,
        # round 17 — the static stamp is one more shape the chain
        # proved unattributable; the corroboration is retired):
        # manual banner, NO revert.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836501981", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )

    def test_advanced_stamp_is_still_ambiguous(self):
        # Given: the LIVE shape — the same paced window, but the
        # landing record's updatedAt ADVANCED past the baseline
        # read's own (two server-authored stamps our reads
        # recorded — same-clock evidence, thread 3836565818; the
        # merge event bumped the record server-side inside the
        # watch). Two resolved surveys: the pre-merge one and the
        # fresh landing's quiet watch.
        surveys = iter(
            [[thread("11", "resolved")], [thread("11", "resolved")]]
        )

        # When: the corroborated window lands.
        code, out, argvs, events = RUNNER.run_guarded(
            surveys,
            iter([open_record("e" * 40)]),
            poll_states=[
                open_landed(STALE_AT),
                open_landed(STALE_AT),
                open_landed(STALE_AT),
                merged_landed(FRESH_AT),
            ],
            merge_rc=1,
        )

        # Then: repinned at round 17 (thread 3836600782) — the
        # ADVANCED stamp attributes NOTHING (the terminal finding:
        # ordered cache snapshots of one historical timeline satisfy
        # every between-reads test), so even the genuinely-fresh
        # landing reports the uniform AMBIGUOUS manual banner: NO
        # assertions, NO survey, NO revert; exit 1.
        self.assertEqual(code, 1)
        self.assertIn("AMBIGUOUS LANDING — MANUAL CHECK REQUIRED", out)
        self.assertIn("3836565818", out)
        self.assertIn("3836600782", out)
        self.assertNotIn("OBSERVED TRANSITION", out)
        self.assertNotIn("MERGED CLEAN:", out)
        self.assertNotIn("REVERT PR OPENED", out)
        self.assertNotIn("git revert", " ".join(argvs))
        self.assertEqual(
            [ev for ev in events if ev == ("survey",)], [("survey",)]
        )


if __name__ == "__main__":
    unittest.main()
