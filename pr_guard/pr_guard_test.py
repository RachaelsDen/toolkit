"""pr_guard test aggregator.

The suites live in pr_guard_classify_test.py (thread classification),
pr_guard_rulesets_test.py (ruleset coverage / fnmatch translation),
pr_guard_merge_test.py (the guarded merge act's post-merge backstop),
pr_guard_merge_watch_test.py (PR #40 round 2: the poll-timeout
pending-merge cancel and the quiet-period watch),
pr_guard_merge_round3_test.py (PR #40 round 3: the deadline-based
quiet watch and the landed-head verification),
pr_guard_merge_round4_test.py (PR #40 round 4: the post-loop final
attempt 2: the post-loop final
completion poll, the clamped quiet sleep, and the narrowed protected
bases), pr_guard_merge_round5_test.py (PR #41: the queue-aware cancel
settlement, the ambiguous merge-command reconcile, and the -R repo
pinning), pr_guard_merge_round6_test.py (PR #41 round 6: the
post-ABSENT state recheck), pr_guard_merge_round7_test.py (PR #41
round 7: the post-ABSENT settling window's mid-window scenarios and
the interrupt reconciliation, thread 3833360219),
pr_guard_merge_round8_test.py (PR #41 round 8: the settling window's
deadline measurement, thread 3833540916, and the parent-shape revert,
thread 3833540921),
pr_guard_merge_round9_test.py (PR #41 round 9, refit round 25:
the two-case single-parent contract — the parent==base-tip plain
revert beside the fail-closed multi-commit landing, threads
3835145976/3835145981/3835175506/3835175508 — and the
dispatch-exception reconciliation, thread 3833671126),
pr_guard_merge_round10_test.py (PR #41 round 10, refit round 25:
the fetch-before-fallback obligation retired with the per-commit
arm it served (thread 3833762316; suite count drops by design),
leaving the canonical-remote pinning, thread 3833762325),
pr_guard_merge_round11_test.py (PR #41 round 11, refit round 25:
the two-case contract against the squash/rebase shapes of thread
3833880596, and the pushurl-safe canonical remote, thread
3833880605),
pr_guard_merge_round12_test.py (PR #41 round 12, refit round 25:
the advancement-interleaved squash fails closed by contract, thread
3833993101, and the github-host validation, thread 3833993106),
pr_guard_merge_round13_test.py (PR #41 round 13, refit round 25:
the fork-diagnostic ref ensuring/degradation, thread 3834093635,
and the deadline-measured queue watch, thread 3834093639),
pr_guard_merge_round14_test.py (PR #41 round 14, refit round 25:
the classifier retirement — the spoof shape fails closed with NO
provenance pipes, thread 3834210484 — and the multi-pushurl remote
validation, thread 3834210476),
pr_guard_merge_round15_test.py (PR #41 round 15: the GraphQL queue
dequeue, thread 3834375737, and the empty-landing fail-closed
classification, thread 3834375731),
pr_guard_merge_round16_test.py (PR #41 round 16: the GH_HOST pin and
startup block, thread 3834400946, the direct diff-tree patch-id
probes, thread 3834400957, the complete-map rebase rule, thread
3834400951, the revert-branch reuse/suffix push, thread 3834400954,
and the temporary-worktree isolation, thread 3834488871),
pr_guard_merge_round17_test.py (PR #41 round 17: the queue settlement
on a failed --disable-auto, thread 3834590317, the bounded dequeue
retries, thread 3834590319, the parent-chain contiguity requirement
for the rebase plan, thread 3834590322, the mergeCommit
pending-poll, thread 3834590326, and the local-branch suffix skip,
thread 3834590328),
pr_guard_merge_round18_test.py (PR #41 round 18: the cancellation
merge-SHA retry, thread 3834666206, the branch-target gate coverage,
thread 3834666208, the merge argv arity gate, thread 3834666210, and
the paginated ruleset fetch, thread 3834666213),
pr_guard_merge_round19_test.py (PR #41 round 19, refit round 25:
the whitespace-drift rebase fails closed by contract, threads
3834761215/3835175506 — the landed-range revert it was built for is
retired), pr_guard_merge_round20_test.py (PR #41 round 20, refit
round 25: the author/subject arm retired with the classifier,
thread 3834819188, leaving the detached-worktree revert push,
thread 3834819191 — registered here at round 21: the round-20
commit created the suite without adding it to this list, the exact
thread-3833251671 omission),
pr_guard_merge_round21_test.py (PR #41 round 21, refit round 25:
the paginated pre-dispatch commit snapshot, threads 3834883632/
3835145981, with the malformed page degrading only the banner
diagnostics — the rewritten-tip and delta suites retired),
pr_guard_merge_round22_test.py (PR #41 round 22, refit round 25:
the documented 250-commit cap discards the pre-dispatch snapshot
with a warning, thread 3834934167 — the delta suites retired with
the arms of threads 3834934170/3834934169),
pr_guard_merge_round23_test.py (PR #41 round 23, refit round 25:
the suffix arm retired with the classifier (thread 3834988955),
leaving the converged-cancel banner reporting the OBSERVED disable
rc with the ignored-because-queued rationale, thread 3834988957),
 pr_guard_merge_round24_test.py (PR #41 round 24, refit round 25:
 the SQUASH MARKER retired to a fail-closed-banner DIAGNOSTIC —
 thread 3835145976 proved a rebase tip's original subject can itself
 end " (#N)", so no marker reading licenses anything — and the
 SHORTENED rebase of thread 3835175508 fails closed (the round-24
 shorter-range squash fall-through is gone),
  pr_guard_merge_round26_test.py (PR #41 round 26, thread 3835290443:
  the single-parent contract compares the landing's parent against
  the FROZEN pre-dispatch base tip — the ordinary squash landing is
  automated again, advancement-past-the-frozen-tip and
  unavailable-snapshot shapes fail closed),
  pr_guard_merge_round27_test.py (PR #41 round 27, thread 3835345690:
  both revert shapes carry the FIXED guard identity in the argv —
  the identity-less automation checkout's "Author identity unknown"
  failure — with read-only probes identity-free and the failure
  banner printing the identity-carrying command),
pr_guard_merge_round28_test.py (PR #41 round 28, thread 3835379480:
both revert shapes carry the unsigned pinning — `-c
commit.gpgsign=false` plus `--no-gpg-sign` — against the
signing-forcing checkout with no usable key, read-only probes
override-free, and the failure banner printing the unsigned command),
pr_guard_merge_round29_test.py (PR #41 round 29, threads
3835450362/3835450365/3835450367: the settle RE-PROBE after a
settling-watch None — a reappearance on the FINAL probe dispatches
the dequeue instead of the timeout banner over a live entry; the
PACED cancellation retries at the re-check cadence (round-6/7
GRAPHQL counts +1 re-probe refit); and the PRE-EXISTING merge
detection — a landing whose mergeCommit equals the pre-dispatch
snapshot (or an already-merged PR) banners without the revert, a
NEW mergeCommit runs the ordinary post-merge path),
pr_guard_revert_trigger_test.py (PR #41 round 7: the truthful
revert-PR copy per trigger, thread 3833360211),
pr_guard_rulesets_harden_test.py (PR #41: the legacy ruleset-name
migration; round 6: the patch-canonical-delete-redundant duplicate
disposal), pr_guard_rulesets_verify_test.py (PR #41 round 7: the
verify-before-delete ordering, thread 3833360207; round 8: the
all-protected-base verification, thread 3833540908), and
pr_guard_rulesets_payload_test.py (PR #41 round 17: the stored-rule
PAYLOAD verification before the fallback deletes, thread
3834590324), split from this
file at the 250 pure-LOC ceiling (PR #37, thread 3828495567). The
shared fakes/runner live in pr_guard_merge_harness — a PLAIN
non-TestCase module (thread 3832660856), so no suite's imports
re-discover another suite's tests; the fake GIT lives in
pr_guard_merge_gitfake and the fixture constants/builders in
pr_guard_merge_fixtures (both plain, same reason).

PR #41 round 25 (threads 3835145976/3835145981/3835175506/
3835175508): the provenance classifier is RETIRED — automated
single-parent coverage is exactly the parent==base-tip shape, every
other single-parent landing fails closed with diagnostics, and the
PR commit list is a pre-dispatch FROZEN snapshot. The exotic-landing
suites were refit to assert the FAIL-CLOSED banner; the redundant
per-arm suites were DELETED with the arms (195 -> 161 tests, the
documented drop of 34): round 9 5->4, round 10 6->4, round 11 6->6,
round 12 6->5, round 13 4->3, round 14 7->4, round 15 5->2,
round 16 12->10, round 17 7->5, round 19 4->1, round 20 4->1,
round 21 7->2, round 22 5->2, round 23 5->2, round 24 6->4.

PR #41 round 26 (thread 3835290443): the comparison target of the
single-parent contract is the FROZEN PRE-DISPATCH base tip (the
round-25 current-ref probe could never match — the pre-revert base
fetch moves the ref to the landing itself or beyond). The new
pr_guard_merge_round26_test pins the ordinary squash landing
AUTOMATED against the frozen tip, the advancement-past-frozen-tip
fail-closed, and the unavailable-snapshot fail-closed
(161 -> 164 tests).

PR #41 round 27 (thread 3835345690): BOTH revert shapes carry the
FIXED guard identity (user.name=pr-guard,
user.email=pr-guard@users.noreply.github.com) pinned in the argv via
pr_guard_common.with_guard_identity — an automation checkout without
a configured identity made `git revert` die with "Author identity
unknown" before the revert commit existed, so the automatic revert
branch/PR never appeared. The new pr_guard_merge_round27_test pins
the identity on both shapes (literal values), the read-only probes
staying identity-free, and the failure banner printing the
identity-carrying command verbatim (164 -> 168 tests).

PR #41 round 28 (thread 3835379480): with_guard_identity also pins
BOTH reverts UNSIGNED — `-c commit.gpgsign=false` (the config
surface: a -c override beats inherited commit.gpgSign=true from any
scope) and `--no-gpg-sign` right after the subcommand (the
command-line surface `git revert -h` exposes; visible in the failure
banner's verbatim command) — because an invoking checkout with
commit.gpgSign=true but no usable signing key made `git revert` die
building the signature before the revert commit existed. The new
pr_guard_merge_round28_test pins both surfaces on both shapes
(literal values), the read-only probes staying override-free, and
the failure banner printing the unsigned command verbatim; the
round-27 literals and the rounds-8/9/11/16/26 argv assertions
track the extended argv (168 -> 172 tests).

PR #41 round 29 (threads 3835450362/3835450365/3835450367): three
P1 fixes. (1) settle_queue_contingency RE-PROBES state+queue after
every settling-watch None — a reappearance on the watch's FINAL
probe consumed the outer deadline while the round-28 code skipped
the dequeue branch on the stale pre-watch ABSENT and returned the
timeout banner over a LIVE entry; (2) the three --disable-auto
attempts are PACED at the CANCEL_RECHECK_SECS cadence (the
back-to-back budget exhausted inside one stale-read interval while
the accepted request stayed live); (3) merge_guarded snapshots the
pre-dispatch merge identity from the head/base REST read and a
landing whose mergeCommit equals the snapshot (or an already-merged
pre-dispatch state) is a PRE-EXISTING merge — a distinct banner,
nonzero exit, NO revert — while a NEW mergeCommit runs the ordinary
post-merge path (the false post-merge watch/revert cycle over an
earlier legitimate merge is gone). The new pr_guard_merge_round29
suite pins all three; the round-6/7 reappearance suites track the
+1 re-probe GraphQL count (172 -> 177 tests).

PR #41 round 30 (threads 3835501549/3835501550): two P1 fixes on the
round-29 coverage. (1) the pre-existing-merge identity gate now rides
the CANCEL/INTERRUPT paths too — a stale invocation whose completion
reads stay unreadable to the timeout, or an operator interrupt,
reached cancel_pending_merge and auto-reverted the HISTORICAL merge
before round-29's late check ever ran; the identity threads
wait_for_merge_completion -> cancel_pending_merge ->
settle_queue_contingency -> the settling watch and the dequeue flow,
and revert_landed_during_cancel gates FIRST (shared banner/verdict
builders in pr_guard_common, where the landed-sha retry read also
moved home). (2) an expired settling watch whose REAPPEARANCE is
followed by an ABSENT re-probe re-enters ONE fresh bounded 30s
re-settlement window (bounded total re-entries: 1) instead of
enforcing the spent outer deadline over a possibly-stale OPEN — the
watch returns a REAPPEARED sentinel so only genuine reappearances
earn the re-entry, and the converged/terminal banners render the
window actually run plus the used re-entry. The new
pr_guard_merge_round30 suite pins both (177 -> 184 tests).

PR #41 round 31 (threads 3835587497/3835587498/3835587500): three
findings plus the pre-emptive LOC splits. (1) the settling watch's
bounded auto-merge re-disables and the exhaustion probe are PACED at
the cancellation re-check cadence — the round-30 form re-probed
immediately, so propagation delay exhausted the budget back-to-back
and the contingency banner fired while the accepted request stayed
live; the exhaustion verdict now rests on a FRESH paced re-read (a
read that no longer says AUTO continues the watch) and the
exhaustion/converged banners report the pacing; (2) the revert
suffix scan REUSES a remote suffix whose head IS this attempt's
revert commit (the deterministic-name match rule) instead of
minting further suffixes toward the 50-name budget; (3) a
successful dequeue whose settlement watch returns plain None keeps
a distinct AMBIGUOUS report clause — only the REAPPEARED sentinel
proves a re-enqueue, so the banners never report false
reappearance evidence. The LOC splits: the settling watch moved to
pr_guard_settle_watch, the harness's fake GH to
pr_guard_merge_ghfake, and harden's pre-DELETE verification findings
to pr_guard_rulesets_verify (harness and rulesets stood at 265/257
pure LOC). The new pr_guard_merge_round31 suite pins all three
(184 -> 189 tests).

PR #43 round 1 (threads 3835653117/3835653120/3835653121): three
P2s. (1) outside a character class a backslash now ESCAPES the next
char (a trailing backslash is end-of-pattern) — Ruby 3.4.4 dir.c's
UNESCAPE/ISEND — so an exclude of refs/heads/\\main actually
excludes main; (2) a bare-negation class [!]/[^] compiles to
any-one-char-except-'/' (bracket()'s ok!=not over an empty body)
instead of a never-match, so an exclude of refs/heads/*[!] excludes
every one-segment ref while the empty POSITIVE class stays
never-match; (3) the revert-branch reuse compares CONTENT
SIGNATURES after sha equality — git patch-id --stable of the fetched
tip vs the freshly-built revert — so a retry's timestamp-fresh
rebuild reuses the pushed branch instead of minting suffixes toward
the 50-name budget. The NEW pr_guard_fnmatch_test suite pins the
two translation fixes (189 -> 194) and the NEW
pr_guard_merge_round32 suite pins the content-signature reuse
(194 -> 197 tests).

PR #43 round 2 (threads 3835714793/3835714798/3835714800/
3835714804): one P1 + three P2s. (1) the patch-id reuse arm
ADDITIONALLY proves ANCESTRY — the fetched tip's parent
(rev-parse FETCH_HEAD^) must BE the base this attempt's revert was
built on (the local HEAD^); a foreign-parent or unreadable probe
takes the suffix path (thread 3835714798); (2) a '-' starting a
negated class body is a LITERAL member (Ruby bracket()'s not_first
rule) — the '/' fold lands AFTER it, closing the [!-x]-shaped
bypass (thread 3835714793); (3) the pre-dispatch identity snapshot
trusts ONLY the merged flags — an OPEN PR's merge_commit_sha is
GitHub's synthetic TEST merge, never pre-merged evidence (thread
3835714800; the round-29 identity suite refit to the ordinary
path); (4) the settling watch's paced exhaustion probe handles
MERGED explicitly through the pre-existing-gated revert instead of
the broad != "AUTO" propagation arm (thread 3835714804). The
pr_guard_fnmatch suite gains the leading-hyphen class (197 -> 199)
and the NEW pr_guard_merge_round33 suite pins the ancestry checks
and the exhaustion-MERGED revert (199 -> 203 tests).

PR #45 round 1 (threads 3835760155/3835760159/3835760162): one P1
commit-omission + one P2 + one P1. (1) the round-33 suite module was
never `git add -f`-ed past the global `.omo/` gitignore — the
aggregator's registration raised ModuleNotFoundError on every clean
checkout and discovery reported 199; the module is committed now
(thread 3835760155); (2) fnmatch_class parses the class body with
Ruby bracket()'s member rule — a '-' is a range OPERATOR only with a
member on BOTH sides and every emitted token is escaped — so the
pathological `refs/heads/[!-0--]ain` compiles (a negated class over
'/', '-' — and, once round 2 corrected the reversed-range arm, '0'
— matching main exactly as
Ruby's FNM_PATHNAME does) instead of raising re.PatternError out of
gate_covers (thread 3835760159; the NEW pr_guard_fnmatch_hyphen
suite); (3) the patch-id reuse arm rejects MERGE tips — `FETCH_HEAD^`
names parent ONE, so a merge candidate with the base as first parent
and foreign history on the second passed; reuse now also requires
`rev-parse FETCH_HEAD^2` to FAIL (single-parent), else the suffix
path (thread 3835760162; the NEW pr_guard_merge_round34 suite pins
the merge-tip rejection and the single-parent reuse; 203 -> 208
tests).

PR #45 round 2 (thread 3835793219): round 1's reversed-range arm
DROPPED both endpoints — but Ruby 3.4.4 dir.c's bracket() memcmps
the test char against EACH ENDPOINT literally BEFORE the interval
guards, which no char survives when left > right, so [m-0] matches
exactly 'm' and '0'. A reversed range now compiles to its two
endpoint LITERALS, closing the [!m-0]-shaped bypass where the
include `refs/heads/[!m-0]ain` translated to `[^/]ain`, matched
main, and let gate_covers certify a merge without the claimed
server-side gate; the hyphen suite's endpoint rows were repinned to
the corrected semantics (208 -> 212 tests; the NEW
pr_guard_fnmatch_reversed suite pins [m-0]/[!m-0] in both
directions and through gate_covers).

PR #45 round 3 (threads 3835846317/3835846318): one P2 + one P1.
(1) the merge-tip reuse probe FAILS CLOSED — `rev-parse
FETCH_HEAD^2` exits nonzero for the missing second parent AND for
transient git failures alike, so the rc==0 boolean read an ERRORED
probe as "not a merge" and reuse proceeded over an unproven tip;
the probe is now a TRI-STATE (rc 0 = merge; rc 128 WITH the
missing-parent stderr signature = PROVEN single-parent; anything
else = UNREADABLE) and only the PROVEN single-parent tip is
reusable (thread 3835846317; the round-34 fixture refit serves the
real rc-128+signature shape, and the NEW round-35 suite pins the
transient-failure suffix path); (2) a stale-OPEN pre-dispatch
record on an already-landed PR made the failed dispatch's reconcile
run with NO identity evidence — the mismatch/DANGER cycle could
auto-revert a historical merge this invocation never dispatched;
the kept open-record sha, the dispatch-time wall clock, and the
landing's committer date now gate the reconciliation through the
NEW pr_guard_identity module (equal sha or a committer date BEFORE
the dispatch = pre-existing banner; unreadable = AMBIGUOUS
manual-check banner; a fresh date = the ordinary post-merge path)
(thread 3835846318; the round-35 suite pins all three arms; 212 ->
218 tests).

PR #45 round 4 (threads 3835877361/3835877364/3835877366/
3835877368): three P1 + one P2. (1) the open-sha arm no longer
trusts bare equality after an ambiguous dispatch — the fresh
landing of an ACCEPTED-but-failed request can REUSE the synthetic
test-merge object the stale OPEN record carried, so the arm now
requires the sha to PROVE a real merge commit through the canonical
remote (fetch + cat-file -t = commit + a resolvable second parent);
synthetic/unresolvable equality falls to the committer-date arm
(thread 3835877361); (2) every cancel/interrupt MERGED verdict runs
the SAME shared pr_guard_identity ladder — revert_landed_during_
cancel receives the open-sha/dispatch-ts/failed-flag evidence
threaded down from merge_guarded, so a stale-OPEN record that only
becomes a visible landing during timeout cancellation or interrupt
settlement is never auto-reverted (thread 3835877364); (3) the
committer-date comparison runs at git's INTEGER-SECOND precision —
the dispatch timestamp is floored, same-second is AMBIGUOUS
(manual banner, no auto-revert), and strictly-before is the only
pre-existing verdict (thread 3835877366); (4) the single-parent
probe is `git rev-parse --verify --quiet FETCH_HEAD^2` classified
by EXIT CODE alone — rc 1 is the quiet form's missing-parent exit
(verified on git 2.55; no stderr to localize), so a non-English
LC_MESSAGES can no longer read every candidate unreadable
(thread 3835877368; the NEW round-36 suite pins the synthetic-sha
fall-through, both cancel-path gates, all three precision arms,
and the localized-stderr reuse; 218 -> 225 tests).

PR #45 round 7 (threads 3836043653/3836043658): two P1s. (1) the
failed-dispatch date arms carry EXACTLY TWO dispositions — round 5's
fixed 300s skew margin let a runner clock >= 300s ahead of GitHub's
certify a FRESH merge as PRE-EXISTING (skipping the base/head
assertions, quiet watch, and revert coverage), so the by-date
pre-existing verdict is RETIRED: UNEQUAL sha + a date clearly AFTER
the dispatch is FRESH (ordinary coverage), everything else is the
AMBIGUOUS manual banner; the successful path's trusted-arms check
is unchanged (rc 0 bounds the landing to after-dispatch). (2) the
revert/result contract is DISTINCT — 0 revert COMPLETED, 3
identity-gate no-revert, 1 revert FAILED (round 6 returned 1 for
all three) — and merge_guarded's final handling branches on the
codes (pr_guard_common.reconciled_exit_summary) so each exit
renders its own summary line and a gated exit never claims a revert
PR exists. The round-35/37 by-date suites are repinned to the
AMBIGUOUS disposition; the NEW round-39 suite pins the ahead-clock
scenario, the unchanged successful path, and all three exit
summaries (231 -> 236 tests).

PR #45 round 8 (thread 3836092104, P1): round 7's remaining FRESH
verdict — UNEQUAL sha + committer date clearly-after — is RETIRED:
a GitHub commit clock ahead of the runner's future-dates
HISTORICAL merges, so the date never proved OUR dispatch landed
it, and the mismatch/head assertions or the automatic revert could
fire on a merge the invocation never dispatched. The failed path's
ONLY fresh attribution is the OBSERVED TRANSITION: the
reconciliation (poll -> cancel -> settlement, one window, the
observation riding a HOLDER dict out of the poll so it survives an
interrupt) watched the state read OPEN/pending after the dispatch
and MERGED later — FRESH regardless of dates/shas, %ct never
consulted; NO transition (the MERGED state already present on the
FIRST post-dispatch read) is AMBIGUOUS whatever the date says. The
round-35 fresh-landing, round-9 dispatch-exception, and round-36/
39 cancel-path suites are repinned (the ambiguous pins need
completion reads that prove NOTHING — UNKNOWN — because an OPEN
read anywhere now attributes the landing fresh); the NEW round-40
suite pins the transition-fresh revert and the
already-merged-on-first-read ambiguous disposition (236 -> 238
tests).

PR #45 round 10 (threads 3836217630/3836217633/3836217635): three
P1s. (1) the transition baseline is the first LIVE post-dispatch
read — one >= ONE REAL POLL INTERVAL (wall clock) past the
dispatch — because a stale-OPEN record can serve BOTH the would-be
baseline and the next read inside that interval (two cached reads
still provide no merge-event provenance); reads inside the first
interval arm and credit NOTHING, the round-5/9/29/35/40/41
transition-fresh suites are repinned to the three-spaced-OPEN
shape (pre-interval, live baseline, credit), and the fake clock's
WALL time now advances with sleep so the rule asserts in exact
fake seconds. (2) an rc-0 `gh pr merge` whose output carries the
already-merged NO-OP signature is classified into the
FAILED-dispatch class for attribution (the identity ladder
applies; only a GENUINE rc 0 keeps the rc-0 bounding). (3) the
completed-revert exit summary states the revert PR is OPEN —
ACTION REQUIRED: an operator must merge it — never "already undid
it" (the round-39 epilogue pin repinned), and the quiet-period
watch split to pr_guard_quiet (merge stood at 247/250 pure LOC,
the split-FIRST rule; the fixture knobs gained merge_noop). The
NEW round-42 suite pins all three (240 -> 244 tests).

PR #45 round 11 (thread 3836277960, P1): the transition baseline
arms on EVERY post-dispatch read of the reconciliation window, not
only the opening ones — round 10 armed the LIVE baseline at the
completion poll and the cancel loop's first read only, so an
interrupt inside the first poll interval carried an EMPTY baseline
into the disable-recheck, the settle probes, the settling watch, and
the post-dequeue verification, all of which only CREDITED against a
baseline that never armed (a settlement that watched the PR OPEN well
past the interval and then merge still passed transition_observed=
False, and the fresh accepted landing was classified AMBIGUOUS — no
assertions, no survey, no revert). The arming/credit pair is now the
ONE shared helper (pr_guard_common.apply_transition_read) run by all
eight read sites, arming on the FIRST LIVE read (>= one real poll
interval past the dispatch) wherever it occurs; immediate-unspaced
reads still arm nothing (round 10's cache rule). The NEW round-43
suite pins the cancel-read arming, the settle-probe arming (the
reviewer's scenario), the dequeue/watch arming, and the
unspaced-stays-ambiguous delta (245 -> 249 tests).

PR #45 round 12 (threads 3836323283/3836323285): the settling
watch's paced EXHAUSTION probe feeds transition tracking (read site
#9 through pr_guard_common.apply_transition_read — with the baseline
still empty its OPEN is the window's first LIVE read and arms it, so
a later loop OPEN credits and the MERGED the watch then reads is
attributed FRESH; unspaced it still arms nothing and the landing
stays AMBIGUOUS), and the merge dispatch's CAPTURED stdout/stderr is
emitted beside both failure summaries (the nothing-landed line and
reconciled_exit_summary's arms) — labeled, truncated to
MERGE_OUTPUT_PREVIEW chars, never shown for a successful dispatch
(the NEW round-44 suite pins both; 249 -> 253 tests).

PR #45 round 13 (threads 3836380780/3836380790/3836380793): three
P1s. (1) a live PENDING arm NORMALIZES to "OPEN" — PENDING (OPEN
with an active auto-merge request) is as live as OPEN (both
unmerged states), so the reviewer's PENDING-baseline window (an
early interrupt, a first-live PENDING cancellation read, live
OPEN/PENDING reads, then MERGED) now credits the transition and
reaches the fresh attribution instead of the ambiguous manual
banner round 12 rendered (its credit arm matched baseline == "OPEN"
only); UNKNOWN/MERGED arms keep their raw verdicts and never
credit. (2) the nested settling watch and the dequeue flow update
the caller's SHARED pr_guard_transition.TransitionEvidence holder
(a new leaf module — common stood at 249/250 pure LOC, split-FIRST)
at each of their probes through the same apply_transition_read
helper, so the watch's armed baseline and credits SURVIVE its
REAPPEARED/None returns for the outer re-probe decision (round 12
threaded the pair as immutable values and the watch's own live OPEN
reads died with its frame). (3) every stage of the reporting-only
committer-date probe (the canonical_remote resolution, the
landing-sha fetch, the %ct log) is CONTAINED — an interrupt or
OSError is an UNREADABLE DATE (the AMBIGUOUS arm) and never
propagates out of the gate, which runs after the completion-wait
exception envelope: round 12 crashed there with NO output at all
after the merge had landed. The NEW round-45 suite pins all three
(254 -> 258 tests).

PR #45 round 14 (threads 3836437093/3836437095/3836437098/3836437100,
3x P1 + 1 P2): ONE coherent revision of the transition baseline/
credit state machine, moved HOME to pr_guard_transition beside the
shared holder (common was back at 250/250 pure LOC). (1) an UNKNOWN
first live read is a TRANSIENT the next valid live read RE-ARMS over
(round 13 froze the raw verdict and later OPEN/PENDING reads could
neither replace it nor credit); (2) a transient MERGED-from-cache
first live read is the same kind of TRANSIENT — rearm replaces
unknown/transient states, NEVER a valid arm (armed is sticky), so a
real OPEN -> MERGED after a cache blip still earns fresh; (3) the
crediting read is SEPARATELY PACED — the arm records baseline_ts and
the credit requires a full interval SINCE THE ARM (a boundary read
arming plus a same-instant read crediting proves nothing); (4) every
interval is measured on time.monotonic() — a wall-clock jump cannot
fake the spacing (the wall-clock dispatch_ts stays for the
committer-date reporting only). The cancel/settle/watch/dequeue
threading collapses onto the SHARED holder (the legacy seed params
are gone), and the round-43/44/45 arming pins are repaced to the
separately-spaced credit. The NEW round-46 suite pins the four
threads' unit and window scenarios (258 -> 267 tests).

PR #45 round 17 (thread 3836600782, P1 — the TERMINAL resolution,
applied to the whole family): the failed-dispatch attribution is
RETIRED. The reviewer's counter-example chain across rounds 7-17
(open-sha reuse 3835944058; the underdetermined precedent
3836003345; clock skew 3835944061/3836043653; the rc-0 no-op
dispatch 3836217633; cached OPEN baselines
3836149500/3836217630/3836277960; PENDING/nested-watch evidence
3836380780/3836380790; the baseline/credit state machine
3836437093/3836437095/3836437098/3836437100; stamp corroboration
3836501981; cross-clock stamps 3836565818; ordered cache snapshots
3836600782) proved NO client-side observation of GitHub's REST
cache can attribute a failed dispatch's landing, so
pr_guard_transition is DELETED, the identity gate's failed arm is
the ONE uniform AMBIGUOUS manual banner (no revert, nonzero exit)
for every observation path, and every former FRESH window pins the
ambiguous disposition now. The dead discriminator suites are
deleted with the machinery (round36 date-precision, round37
margin, round45 state-machine unit + contained-probe, round46
state-machine units, round47 corroboration units); the
successful-path suites are unchanged (276 -> 255 tests).

The sibling suites are imported ONLY inside load_tests, via importlib
(release-merge regression fix: the old module-level imports let the
aggregator hook re-register suites that unittest discovery had already
loaded from their own files, so every test ran twice — Ran 100 for 50
tests). Under discovery (pattern is not None) each sibling file is
loaded directly, so the hook defers and adds nothing; run directly
there is no discovery pass over the siblings, so the hook aggregates
every suite — either way every test runs exactly once.

pr_guard_reaction_test (PR #48, vault note 'Unified Realms/Notes/
Codex Review Bot Reaction Signal.md'): the codex review-bot PR
reaction — bot_review_reaction's latest-wins parsing (unknown latest
-> NONE), the fail-open survey banner, the wait mode's flip/timeout/
unreadable poll loop on the FakeClock, and the wait argv contract
(260 -> 280 tests).

pr_guard_reaction_followup_test (PR #49, threads 3867503705/
3867503708/3867503712): the reaction follow-ups — paginated
gh_reactions, deadline-bounded probe budgets, and the stale-round
THUMBS_UP discrimination. PR #49 round 2 (threads 3867572256/
3867572265): every probe's subprocess timeout is the ACTUAL
remaining window (recomputed per subprocess — each reactions page,
the head-date read — capped at two intervals, floored at 1s so the
at-deadline final probe still reads), and the suite is REGISTERED in
_SUITES — the round-1 commit added the module without touching this
list (the recurring round-33 omission class, thread 3835760155's
twin: the documented aggregate command skipped its tests while the
suites below stayed green), so the aggregate count moves 280 -> 295
(the suite's 15 tests, +2 for the round-2 recompute/clamp pins).

pr_guard_reaction_round3_test (PR #49 round 3, threads 3867653639/
3867653642): completion bound to the ACTUAL requested round — a
THUMBS_UP must postdate the head push AND the latest round-engagement
marker (the timeline ReviewRequestedEvent's createdAt, a re-request
with no head change, beside the bot's latest SUBMITTED review — this
repo's rounds engage without formal requests, REST- and GraphQL-
agreed live 2026-08-27, so the submission is the same-head marker
that exists) — and the survey banner's informational read bounded by
BANNER_TIMEOUT_SECS, a stall failing open to UNREADABLE instead of
hanging survey/pre-merge/the quiet watch (295 -> 305 tests).

pr_guard_reaction_round4_test (PR #49 round 4, threads 3867757439/
3867757442/3867757445/3867757449): the marker set gains the bot's
latest review-THREAD comment (a request-less round that has begun
posting marks itself, so the prior +1 reads stale mid-round), request
events are FILTERED to the codex reviewer (a human/other-bot request
after the pass extends nothing), gh_reactions STOPS at an expired
deadline returning the stderr-marked partial walk (never a fresh 1s
floor grant per page), and the informational banner is kept OUT of
gate surveys — survey(reaction=False) for the guarded merge's
closing survey, banner-after-summary everywhere else. The gate
companion suite pr_guard_reaction_round4_gate_test carries the
thread-3867757449 survey/merge-act discipline (the 250 pure-LOC
ceiling split — tests included) (305 -> 319 tests; the round-3
probe fixtures repinned to the round-4 wire shape:
requestedReviewer on request events, reviewThreads window).

pr_guard_reaction_round5_test (PR #49 round 5, threads 3867897759/
3867897764/3867897766): the post-merge quiet watch runs bannerless
(every cycle's DANGER check and the final MERGED CLEAN verdict —
survey(reaction=False)), an expired reactions walk RAISES
ReactionWalkExpired (the partial page list is UNREADABLE — the
banner fails open, the wait keeps polling), and a THUMBS_UP already
present at wait start needs the wait to OBSERVE one confirmed
non-DONE reading before exit 0 (319 -> 327 tests; registered with
PR #49 round 6, thread 3868047715 P2 — the suite had shipped
unregistered, so the aggregate ran 319 without it).

pr_guard_reaction_round6_test (PR #49 round 6, threads 3868047715/
3868047719): unreadable round bounds read THUMBS_UP_UNVERIFIED — a
state distinct from a verified THUMBS_UP_STALE that never arms the
transition latch (the transient-bounds-failure + persistent prior
+1 shape times out exit 1 instead of exiting 0 on an error-armed
latch; a recovered-bounds EYES still arms and the fresh +1 exits
0), and the state vocabulary/latch live in the sibling
pr_guard_reaction_latch (the reaction module's 250 pure-LOC
ceiling split) (327 -> 333 tests).

pr_guard_reaction_round7_test (PR #49 round 7, threads 3868158293/
3868158297/3868158304): the initial-held +1's wait accepts an
OBSERVED-NEW +1 — the +1's identity (created_at|id) compared
across probes, so a fast EYES->+1 round entirely between two
probes still exits 0 while an unchanged old +1 keeps timing out;
pre-merge's CLOSING survey runs bannerless (reaction=False, the
merge act's decision-surface rule); and the request-event timeline
is read through a paginated latest-50 window BEFORE the codex
filter (a current codex request can no longer vanish behind five
unrelated requests — a failed or expired walk reads the bounds
unreadable, never a missing marker biasing done). The timing
discipline and round_bounds moved to the sibling
pr_guard_reaction_probe at the same split (333 -> 345 tests; the
round-3/4/followup probe fixtures repinned to the module's
subprocess seam; the gate companions live in
pr_guard_reaction_round7_gate_test, the 250 pure-LOC ceiling —
tests included — split of the round-4 suite-pair precedent).

pr_guard_reaction_round8_test (PR #49 round 8, thread 3868443452
P1): the head-change latch reset — round_bounds PRESERVES the
headRefOid ROUND_QUERY always carried (the reading is now
(head_oid, pushed, marker), read on EVERY probe, EYES and NONE
included), and the wait RESETS the transition latch and the
+1-identity baseline the moment the oid changes: a head moved onto
an already-pushed commit whose pushedDate predates the standing +1
reclassified the UNCHANGED reaction stale->done across two probes
and exited 0 on a pre-move pass. An unchanged old +1 after the
flip now holds to the timeout while a genuine post-flip
EYES->+1 round still exits 0 (the reset runs before the probe's
own reading contributes, so an EYES under the NEW head re-arms);
an unreadable oid never certifies a change nor pollutes the
baseline. Every seam fixture that pins round_bounds repinned to
the head-first triple (345 -> 349 tests).

pr_guard_reaction_round10_test (PR #49 round 10, threads
3868782039 P1/3868782042 P1): the head STABILITY bracket —
bot_reaction_reading reads the head oid FIRST (the probe module's
new head_ref_oid), then the reactions, then the round bounds (ONE
combined query carrying the after-side oid beside its dates), and
a head that MOVED between the reads raises ReactionHeadMoved: the
whole probe is UNREADABLE (retry next interval), never a mixed
snapshot the wait could reset-and-re-arm from — the reviewer's
race paired an EYES for head A with head B's OID, and a completion
for A arriving after B's push then satisfied B's bounds and exited
0 without B being reviewed (an unreadable side '' certifies
nothing). And equal-second round facts are AMBIGUOUS:
thumbs_up_round_state's comparisons became `<=` (only
STRICTLY-greater created_at is DONE; equality reads THUMBS_UP_STALE),
so a prior-round +1 landing in the same second as a head push or
re-request cannot ride an armed latch to exit 0 (355 -> 363 tests;
the attr-seam fixtures gained the head_ref_oid patch).

pr_guard_reaction_round11_test (PR #49 round 11, threads
3868979509 P1/3868979515 P2/3868979526 P2): the observed EYES
binds the CURRENT head's push (eyes_round_state in the latch
module — a pre-head EYES reads EYES_STALE and an unreadable push
EYES_UNVERIFIED, NEITHER latch-arming, so head A's late completion
+1 postdating head B's timestamps cannot ride a stale-EYES-armed
latch to exit 0; the binding is the head push only, never the
marker, because a request-less round's comments land after its own
EYES); every probe reads under ONE SHARED budget (the head read,
the walk, and the round probe all consume the start-of-probe
deadline — the walk receives the raw remaining and its <=0 guard
stops the probe UNREADABLE, never a fresh per-stage grant); and
resolve's FINAL AUDIT survey runs bannerless (reaction=False — its
DANGER check gates the RESOLVE DONE verdict, the decision-surface
rule; the OPENING survey keeps the banner). The banner itself
moved to the sibling pr_guard_reaction_banner (reaction.py hit the
ceiling; imports one way, the reading called THROUGH the reaction
namespace so every patch seam stays at one home) (363 -> 372
tests).

pr_guard_reaction_round12_test (user-taught refinements #2, vault
note section 'User-taught refinements #2'): EYES -> NONE = review
completed WITH FINDINGS — the confirmed transition (a NONE that
persists through the probe after a current-head-verified EYES)
exits the NEW code 3 with the WAIT FINDINGS line, while a lone
transient NONE (the non-atomic remove-EYES-then-post-+1 switch)
keeps polling; stale/unverified EYES never arm it and a head move
resets the arming with the latch; a COLD NONE (no EYES variant
ever observed) past COLD_NONE_GRACE_SECS prints the '@codex
review' trigger HINT exactly once and keeps polling; the exit-code
table (0 pass / 1 timeout / 2 usage / 3 findings) is pinned; and
the NONE render/banners carry the refinements-#2 wording. The
reactions walk (gh_reactions) moved to pr_guard_reaction_probe at
this round's 250 pure-LOC ceiling (re-exported, seams unchanged)
(373 -> 382 tests).

pr_guard_suites_committed_test (PR #49 round 11, thread 3868979520
P2 — the FOURTH .omo gitignore add -f occurrence): every module
referenced in _SUITES must exist as a COMMITTED blob in HEAD — the
round-10 suite shipped registered-but-uncommitted and the
aggregate passed locally while failing the clean checkout with
ModuleNotFoundError; the guard fails until `git add -f` lands, and
skips in a git-archive extraction where the aggregate import is
itself the guard (372 -> 373 tests).

pr_guard_reaction_round13_test (PR #49 round 13, threads
3869259808/3869259813/3869453944/3869453955 P1 +
3869453959 P2): the head STABILITY bracket rejects either empty
endpoint (ReactionBracketUnreadable — the whole probe UNREADABLE,
retry next interval; THUMBS_UP_UNVERIFIED survives via the
readable-oid/null-dates shape); the accepted EYES binds the formal
codex REQUEST marker round_bounds now returns separately (4-tuple:
head oid, pushed, request, composite marker) while post-EYES
thread-comment markers never bind it (the round-11 asymmetry);
post-head-transition the EYES binds the transition OBSERVATION (the
wait's own wall clock — transition_floor into the reading, plus the
transition probe's own demotion that also suppresses the held +1
baseline); replaced_plus_one requires the strictly NEWER identity
(reaction_follows ordering); and the head-move reset clears the
cold-NONE detector (saw_any_eyes/hint state) with the latch.
Split-first at the ceiling: the wait loop + wall_iso_z +
COLD_NONE_GRACE_SECS moved to the NEW sibling pr_guard_reaction_wait
(called THROUGH the reaction namespace — the round-11 banner rule —
so every time/probe patch seam keeps ONE home; re-exported for
pr_guard.py) (382 -> 393 tests).

pr_guard_reaction_round14_test (PR #49 round 14, threads
3869941505 P1/3869941521 P1) + pr_guard_reaction_round14_unknown_test
(3869941509 P2 — the 250 pure-LOC ceiling's suite-pair split, tests
included, the round-4/round-7 precedent): the transition-NONE
arming gate (post-head-move a NONE does not arm the latch until a
post-floor EYES or a post-observation marker certifies the new
head's round — the old head's non-atomic switch window; the marker
opener RETIRED in round 16, see pr_guard_reaction_round16_test;
cold-start NONE under a stable head still armed, round 5 preserved
— REPINNED in round 15, see below); the DISTINCT REACTION_UNKNOWN state for
unrecognized latest content (never NONE — refinements #2 made
persistent NONE the terminal findings exit; never arms, never
satisfies the findings transition or the cold-NONE hint, breaks
NONE persistence, renders its content); and the resurfaced prior
+1 as the SECOND completion-absent shape (a THUMBS_UP proven
older than the observed arming EYES — DONE-classified yet not
following the watermark — confirms findings with the same two-probe
persistence/verified-EYES precursor/head-reset discipline; the
watermark only moves FORWARD now: an arming NONE refreshes nothing)
(393 -> 407 tests; the reaction_test unknown-content pair and the
round-9 predating-+1 watermark fixture repinned — the exact holes).

pr_guard_reaction_round15_test + pr_guard_reaction_round15_probe_test
(PR #49 round 15, threads 3870293188 P1/3870293194 P1/3870293197
P1/3870293205 P1 — the suite-pair split at the ceiling again, the
round-14 precedent): the REQUEST-marker high-water over the
reading's new SIXTH element (baseline on first observation,
round-latch reset on strict mid-wait advancement — the gate re-open
it shipped is RETIRED in round 16, see below — so the re-request
cannot keep the old round's latch/watermark certified while its
delayed +1 postdates the new request); the COLD-START
head-transition bound (round_bounds MAXes the latest
HeadRefForcePushedEvent createdAt into the head bound — live-
verified: no HeadRefPushedEvent timeline item exists, and a
retarget onto already-pushed history is by definition a force
push — so a retarget onto an already-pushed commit reads the old
head's leftover EYES STALE while a normal fresh push (fresh-commit
dates) is unchanged, and the bound is the EVENT, never the
wait's own start clock); the PARTIAL-ERROR unreadable probe
(codex_request_marker requires the timelineItems CONNECTION SHAPE,
round_bounds rejects any top-level GraphQL errors array, and every
sibling connection gets the same _nodes hygiene — a missing request
connection is unreadable per round 13's bracket rule, never a
readable no-request); and the COLD-NONE arming gate at WAIT START
(none_arming_gated initializes True; openers per round 15: a
verified EYES, or a request/marker high-water ADVANCE mid-wait —
REDUCED by round 16 to the verified EYES alone, see below; a fast
round starting inside a cold-NONE window conservatively holds to
timeout, the accepted price, while round 5's initial-+1 shape still
exits 0 via the REPLACEMENT path) (407 -> 423 tests; round-14's
test_cold_start_none_still_arms repinned to the reversed rule — the
exact hole, documented in its Given/When/Then).

pr_guard_reaction_round16_test (PR #49 round 16, threads 3870734078
P1/3870734085 P1): the EYES-only NONE-gate openers — markers and
requests carry NO head/round identity (a still-running review of
the OLD head posts markers after a transition floor; a re-request
says nothing about which job's reactions follow it), so neither can
certify the round a NONE would arm against: the ONLY opener of
none_arming_gated is a verified EYES (state == REACTION_ACTIVE,
the one classification binding the head push, the formal request,
and the transition floor — rounds 11/13/15). Retired: round-14's
post-floor marker opener (3870734085) and round-15's request/marker
ADVANCE openers (3870734078); KEPT: the request-advance latch reset
(3870293188 — protective), which now RE-CLOSES the gate (a re-request
supersedes the old round's certifications, a gate its EYES opened
included), the mid-wait head-move gate set, and the cold-start True
initialization. The non-stranding survivor pins a verified
POST-REQUEST EYES re-opening the gate in the same probe; the
conservative NONE->+1-with-no-EYES hold is the accepted price
(round-15 precedent) with the replacement path intact (423 -> 427
tests; the three exact-hole repins — round-14's
test_post_observation_marker_clears_the_gate and round-15's
test_request_advance_opens_the_cold_none_gate +
test_marker_advance_midwait_opens_the_gate — documented in the
round-16 commit body).

pr_guard_reaction_round17_test + pr_guard_reaction_round17_probe_test
+ pr_guard_reaction_round17_evidence_test (PR #49 round 17, threads
3870995905 P1/3870995911 P1/3870995919 P1 — the suite-pair-plus
split at the ceiling, the round-14 precedent): the REQUEST high-water consumes boundary
IDENTITIES `createdAt|node id` (request_advances: strictly-newer
createdAt OR a same-second DISTINCT node id — the base64 GraphQL id
carries no chronology, ReviewRequestedEvents have no databaseId),
so a re-request landing inside the standing request's timestamp
second still resets the round latches and re-closes the gate; the
documented '@codex review' TOP-LEVEL comment trigger (ANY author,
case-insensitive substring) joins the boundary stream through
ROUND_QUERY's aliased triggerComments connection + a backwards
walking twin (the same bounded-window/pagination/shape hygiene as
every read) — a posted trigger while the wait observes a preceding
round advances exactly like a re-request, a pre-wait trigger is
the cold-start baseline; and the accepting +1 gains the HEAD-BOUND
completion check post-move (the EYES-gate corollary: the EYES still
opens the gate, but the +1 completes only when the latest BOT
review's commit oid == the observed head — latest_review_commit in
the evidence suite, live-verified commit{oid} on submitted reviews;
a request-less cold start keeps today's behavior and never calls
the seam, an unreadable read withholds). Thread 3870995914 (bound
fast-forward ref moves) shipped NO probe change: the live schema rejects every
candidate boundary (pullRequest.pushedDate undefinedField;
HEAD_REF_PUSHED_EVENT still not a timeline type; PullRequestCommit
has no association timestamp) — the FF cold-start gap is documented
in the receipts/vault, and its mid-wait flavor is closed by the
head-bound completion check. The boundary walks + bot vocabulary +
timing clamps moved to the NEW sibling pr_guard_reaction_boundaries
(re-exported through the probe module; every seam keeps one home)
(427 -> 444 tests; the four post-move-survivor harnesses round8/
round10/round13/round14 feed the new latest_review_commit seam with
the post-move head's review — fixture-seam maintenance in the
round-8 precedent, every assertion untouched, documented in the
round-17 commit body).

pr_guard_reaction_round18_test + pr_guard_reaction_round18_probe_test
(PR #49 round 18, threads 3871485035 P1 / 3871485043 P2 /
3871485055 P1): the review evidence is FOLDED into ROUND_QUERY's new
author-filtered botReviews connection — reviews(last:1,
author:"chatgpt-codex-connector[bot]", live-verified server-side
filter) — so the head-bound completion check consumes the reading's
eighth element under the SAME stable-head bracket that certifies the
head oid (3871485035's separate post-bracket lookup and 3871485043's
evictable latestReviews(last:10) window are both gone; latest_review
commit is now the extraction over the round-query node — the
round17_evidence suite REPINNED to the folded seam, an exact-hole
encoding of the condemned lookup mechanics); the formal request and
the trigger comment retain SEPARATE per-kind high-waters (3871485055
— each with the round-17 identity distinctness; the reset + gate
re-close fire when EITHER advances; the merged boundary survives for
CLASSIFICATION only). round_bounds returns a 4-field RoundBounds
tuple SUBCLASS — equality with every legacy plain-4-tuple seam
fixture preserved (the zero-repin seam rule), the three round-18
facts ride as .request/.trigger/.review_head attributes — and the
five post-move-survivor harnesses (round8/10/13/14/17) feed the
folded attr where they fed latest_review_commit (fixture-seam
maintenance in the round-17 GOTCHA precedent, every assertion
byte-identical) (444 -> 455 tests).

pr_guard_reaction_round19_test + pr_guard_reaction_round19_boundary_test
+ pr_guard_reaction_round19_walk_test (PR #49 round 19, threads
3871844565 P1 / 3871844567 P2 / 3871844576 P2 / 3871844580 P2 — the
suite-triple split at the 250 pure-LOC ceiling, the round-17
suite-pair-plus precedent): the REQUEST-ADVANCE OBSERVATION FLOOR
(3871844565 — a same-head re-request landing after the old job
launched but before it posted EYES leaves the old EYES postdating
the request, so the advance probe's reset + gate re-close were undone
in the same iteration and the old job's +1 exited 0 before the newly
requested round ran; the wait now stamps its own wall clock at the
advance observation and post-advance DEMOTES any EYES predating that
stamp to the wait-side EYES_STALE — arming nothing, withheld forever
— while a post-observation EYES certifies; the documented residue: a
post-observation old-job EYES is temporally indistinguishable from
the new job's at the reaction API, backstopped by the quiet watch +
rulesets); the COLD-NONE reset on the request-advance (3871844567 —
saw_any_eyes/cold_none_since/cold_hinted clear with the latch, the
round-13 head-move symmetry, so a never-starting re-requested round
hints at the 10s mark instead of holding the prior round's EYES
suppression to timeout); the per-kind boundary identity SETS
(3871844576 — retention records EVERY identity seen per kind, an
advance needs an UNSEEN identity passing the round-17 compare, so a
deleted-then-resurfaced same-second comment never readvances and
visibility oscillation is inert — boundary_advances in the latch);
and the REST walk's MUTATION detection (3871844580 — a duplicate id
across consecutive pages, a boundary created_at inversion, or a
same-second boundary id regression raises ReactionWalkExpired: probe
UNREADABLE, retry next interval, never latest-wins on an internally
inconsistent walk; the pure-deletion omission residual documented —
no local signature exists, the next probe's settled re-read
recovers) (455 -> 464 tests).

pr_guard_reaction_round20_test + pr_guard_reaction_round20_probe_test
(PR #49 round 20, threads 3872194007 P2 / 3872194017 P2 /
3872194023 P1): the FULL-IDENTITY boundary streams (3872194007 —
the walks' collect sets record EVERY visible same-second identity
at the high-water second and the wait's seen-sets union them, so a
sibling resurfacing after the newest of its second is deleted never
counterfeits an advance; a genuinely-new same-second boundary still
advances); the REQUEST-BOUNDARY FLOOR (3872194017 — the OWNED
SUPERSESSION of round 19's observation floor: a between-polls EYES
of a legitimately requested round certifies against the REQUEST/
TRIGGER's own createdAt — the reading's round-13 binding — instead
of the poll's wall clock, which staled the new round's own startup
EYES to timeout; the round-19 pin repinned as the documented exact
hole, the false-exit class backstopped by the quiet watch +
rulesets); and the REVIEW-STATE completion bind (3872194023 — the
`state` field live-verified NOT to separate findings from passes
(COMMENTED on #49's findings rounds and #48's pass round alike), so
the built guard binds the completing +1 to the folded verdict
stamp: post-move the latest head-bound bot review must submit
after the transition floor AND be followed by the +1 — the
stale-review retarget coincidence and the verdict-predates-review
eviction shape close, the exact out-of-order same-era race
documented-open) (464 -> 473 tests).
Round 21 (threads 3872631145 P2 / 3872631157 P2, PR #49): the
head-bound FINDINGS exit (the EYES -> NONE completion path gained
the THUMBS_UP exits' post-transition evidence legs — review_head ==
observed head AND review_stamp > the transition floor, the
+1-follows-stamp leg moot; an old head's still-running job posting a
post-floor EYES, finishing with feedback, and removing it can no
longer exit 3 under a head it never reviewed) and the CROSS-PAGE
same-second collection (both boundary walks continue into the
preceding page when the answering page's OLDEST item shares the
selected marker's second, collecting that second's identities while
the fetched page's newest still shares it — a straddling sibling
the round-20 in-page fill never saw could resurface after the
in-page newest's deletion and counterfeit a boundary advance;
unreadable continuation -> the whole walk unreadable, legacy 3-arg
callers never continue) (474 -> 483 tests).
Round 25 (threads 3873970919 P2 / 3873970927 P1 / 3873970933 P1,
PR #49): the per-page walk revalidation (every FULL page the
reactions walk fetched is re-read after the walk completes and its
newest item identity required unchanged — round 24's page-1 recheck
could not see a page-2-range deletion shift page 3, silently
skipping its former first reaction, the bot's current EYES included;
the short final page shifts nothing and is never re-read), the
STRICT rerun connections (the round-24 bracket re-run of our own
assembled query now REQUIRES a present, well-formed triggerComments
— an omitted field is the partial/malformed class, never
"provably no trigger"; the INITIAL query's legacy-absent-key
tolerance stays, the asymmetry pinned), and the COLD-START
head-bound completions (both +1 exits and the findings exit require
the folded review to name the observed head floored or not — the
pre-fix floored-only leg skipped it entirely when the wait started
after a head change, letting the old head's still-running job exit
0 on reactions that postdated the new push; '' review_head
withholds, the stamp/floor legs stay floored-only, round 17's
cold-start-skip pin repinned as the documented exact hole) (516 ->
532 tests).
Round 27 (threads 3874769241 P2 / 3874769245 P1 / 3874769253 P2,
PR #49): the same-second verdict (the +1-follows-stamp completion
leg is equality-safe `>=` — the round-27 supersession of the
round-10 strictness FOR THIS LEG ONLY; a review submission and its
immutable +1 verdict sharing one API second no longer strands the
passed round to timeout, the classification legs keep strict `>`),
the BASE-change reset + floor (baseRefOid joins ROUND_QUERY/round_
bounds/the Reading as .base/.base_bound attrs — the zero-repin seam
rule; a retarget or base-tip advance under an UNCHANGED head fires
the head-move reset family and stamps base_floor = the boundary's
OWN timestamp, BaseRefChangedEvent createdAt or the base target's
own push bound, into floor = max(transition, boundary, base) — the
review's commit.oid names the HEAD, so the stamp leg IS the
separation; live-verified read-only: baseRefOid/baseRef.target
exist, BASE_REF_CHANGED_EVENT is a valid timeline item whose shape
materializes on microsoft/vscode#101656 while PR #49 carries zero
events, and the live base's pushedDate reads NULL so the
committedDate fallback is live-relevant), and the DEADLINE-CROSSING
final probe (the timeout fires only when a probe BEGAN at-or-after
the deadline; an overlong earlier probe yields exactly ONE more
fresh reading — the promised final probe — then the timeout) (538
-> 552 tests; the suite TRIPLE split at the 250 pure-LOC ceiling,
the round-19/25 precedent).

Round 28 (threads 3875089260 P1 / 3875089268 P1 / 3875089273 P1,
PR #49): the cold-start base floor (a wait starting AFTER the base
already changed left base_floor '' — the completion stamp checks
were skipped and an old-base review of the UNCHANGED head exited 0
with review_head == observed_head trivially true; the first
readable probe now initializes base_floor ALONGSIDE observed_base —
an initialization, never a change: no reset family fires, the
boundary baseline rule — and post-cold-start stale-base completions
fail review_stamp > base_floor, the mid-wait stamp's same
separation), the BRACKETED BASE (the pagination re-run now carries
the base oid beside the head — round-25 strict doctrine: our own
assembled query always materializes baseRefOid, so an absent key or
a mismatch during the walks' continuation reads is UNREADABLE
bounds, never the ORIGINAL base certified over a move the next
poll would only catch an interval later; the INITIAL query's
legacy absent-key tolerance stays), and the RETURNING-OID
transitions (a head cycling A->B->A between polls leaves the oid
unchanged while the reading's head_bound strictly advances — the
force-push event genuinely moved, round-15/26 semantics — so the
retained observed_head_bound's advance fires the SAME reset family
as a move and transition_floor advances to the new bound: the
pre-cycle job's review fails the stamp leg and its delayed +1 can
no longer ride the pre-cycle EYES to WAIT DONE) (552 -> 560 tests;
the suite PAIR split at the 250 pure-LOC ceiling, the round-27
precedent; six paginating-fixture builders gained baseRefOid —
round-25 seam maintenance, every assertion byte-identical).

pr_guard_wait_accept_standing_test (user request 2026-08-28, no
thread ID — the standalone repo's first post-extraction feature):
the wait mode's --accept-standing opt-in fast path for ALREADY-PASSED
PRs — a standing DONE-classified THUMBS_UP exits 0 immediately,
bypassing the round-5 observation gates and the round-17/18/20/22/25
review-evidence legs (the zero-review-object '' shape included: every
zero-findings pass posts no review object), while the +1's own
staleness CLASSIFICATION still applies (a +1 predating the head push
reads THUMBS_UP_STALE and holds — only state == REACTION_DONE
accepts) and the flagless default path is pinned byte-identical (the
argv strip works in either flag order; the flagless dispatch keeps
its historic two-arg shape) (596 -> 603 tests).

Run: cd .omo/start-work && python3 -m unittest pr_guard_test -v
No network: every suite is pure; nothing shells out to gh.
"""

import importlib
import unittest

from .pr_guard_repo import configure

_SUITES = (
    "pr_guard_classify_test",
    "pr_guard_fnmatch_test",
    "pr_guard_fnmatch_hyphen_test",
    "pr_guard_fnmatch_reversed_test",
    "pr_guard_merge_round3_test",
    "pr_guard_merge_round4_test",
    "pr_guard_merge_round5_test",
    "pr_guard_merge_round6_test",
    "pr_guard_merge_round7_test",
    "pr_guard_merge_round8_test",
    "pr_guard_merge_round9_test",
    "pr_guard_merge_round10_test",
    "pr_guard_merge_round11_test",
    "pr_guard_merge_round12_test",
    "pr_guard_merge_round13_test",
    "pr_guard_merge_round14_test",
    "pr_guard_merge_round15_test",
    "pr_guard_merge_round16_test",
    "pr_guard_merge_round17_test",
    "pr_guard_merge_round18_test",
    "pr_guard_merge_round19_test",
    "pr_guard_merge_round20_test",
    "pr_guard_merge_round21_test",
    "pr_guard_merge_round22_test",
    "pr_guard_merge_round23_test",
    "pr_guard_merge_round24_test",
    "pr_guard_merge_round26_test",
    "pr_guard_merge_round27_test",
    "pr_guard_merge_round28_test",
    "pr_guard_merge_round29_test",
    "pr_guard_merge_round30_test",
    "pr_guard_merge_round31_test",
    "pr_guard_merge_round32_test",
    "pr_guard_merge_round33_test",
    "pr_guard_merge_round34_test",
    "pr_guard_merge_round35_test",
    "pr_guard_merge_round36_test",
    "pr_guard_merge_round37_test",
    "pr_guard_merge_round38_test",
    "pr_guard_merge_round39_test",
    "pr_guard_merge_round40_test",
    "pr_guard_merge_round41_test",
    "pr_guard_merge_round42_test",
    "pr_guard_merge_round43_test",
    "pr_guard_merge_round44_test",
    "pr_guard_merge_round45_test",
    "pr_guard_merge_round46_test",
    "pr_guard_merge_round47_test",
    "pr_guard_merge_round48_test",
    "pr_guard_merge_test",
    "pr_guard_merge_watch_test",
    "pr_guard_reaction_followup_test",
    "pr_guard_reaction_round10_test",
    "pr_guard_reaction_round11_test",
    "pr_guard_reaction_round12_test",
    "pr_guard_reaction_round13_test",
    "pr_guard_reaction_round14_test",
    "pr_guard_reaction_round14_unknown_test",
    "pr_guard_reaction_round15_test",
    "pr_guard_reaction_round15_probe_test",
    "pr_guard_reaction_round16_test",
    "pr_guard_reaction_round17_test",
    "pr_guard_reaction_round17_probe_test",
    "pr_guard_reaction_round17_evidence_test",
    "pr_guard_reaction_round18_test",
    "pr_guard_reaction_round18_probe_test",
    "pr_guard_reaction_round19_test",
    "pr_guard_reaction_round19_boundary_test",
    "pr_guard_reaction_round19_walk_test",
    "pr_guard_reaction_round20_test",
    "pr_guard_reaction_round20_probe_test",
    "pr_guard_reaction_round21_test",
    "pr_guard_reaction_round21_walk_test",
    "pr_guard_reaction_round22_test",
    "pr_guard_reaction_round22_boundary_test",
    "pr_guard_reaction_round22_probe_test",
    "pr_guard_reaction_round23_test",
    "pr_guard_reaction_round24_test",
    "pr_guard_reaction_round24_probe_test",
    "pr_guard_reaction_round25_test",
    "pr_guard_reaction_round25_wait_test",
    "pr_guard_reaction_round26_test",
    "pr_guard_reaction_round27_probe_test",
    "pr_guard_reaction_round27_test",
    "pr_guard_reaction_round27_wait_test",
    "pr_guard_reaction_round28_probe_test",
    "pr_guard_reaction_round28_test",
    "pr_guard_reaction_round29_test",
    "pr_guard_reaction_round30_test",
    "pr_guard_reaction_round31_test",
    "pr_guard_reaction_round32_probe_test",
    "pr_guard_reaction_round32_test",
    "pr_guard_reaction_round33_test",
    "pr_guard_reaction_round3_test",
    "pr_guard_wait_accept_standing_test",
    "pr_guard_reaction_round4_gate_test",
    "pr_guard_reaction_round4_test",
    "pr_guard_reaction_round5_test",
    "pr_guard_reaction_round6_test",
    "pr_guard_reaction_round7_gate_test",
    "pr_guard_reaction_round7_test",
    "pr_guard_reaction_round8_test",
    "pr_guard_reaction_round9_test",
    "pr_guard_reaction_test",
    "pr_guard_revert_trigger_test",
    "pr_guard_rulesets_harden_test",
    "pr_guard_rulesets_payload_test",
    "pr_guard_rulesets_target_test",
    "pr_guard_rulesets_test",
    "pr_guard_rulesets_verify_test",
    "pr_guard_suites_committed_test",
)


def load_tests(loader, tests, pattern):
    # The toolkit extraction's TEST-FIXTURE DEFAULT: the suites below
    # pin the historic development repository (RachaelsDen/
    # UR-lorebook) in their argv/URL/banner assertions, so configure()
    # re-pins it here before ANY suite loads. Under discovery
    # (pattern is not None) the sibling files import alphabetically
    # BEFORE this hook runs — configure()'s from-import walk keeps
    # every already-imported pr_guard module coherent with the
    # fixture, and modules importing later bind it directly; the
    # library's own resolution (flag -> env -> origin remote) lives
    # in pr_guard_repo/pr_guard.cli.run, never in the test paths.
    configure("RachaelsDen", "UR-lorebook")
    if pattern is not None:
        return loader.suiteClass(tests)
    suite = unittest.TestSuite()
    for name in _SUITES:
        module = importlib.import_module(f"{__package__}.{name}")
        suite.addTests(loader.loadTestsFromModule(module))
    return suite


if __name__ == "__main__":
    unittest.main()
