"""The shared fixtures for the merge-act suites: the well-known shas,
expected-argv constants, the fake clock, and the PR/queue record
builders.

Split from pr_guard_merge_harness.py at the PR #41 round-11 fixes:
the harness stood at 247/250 pure LOC (HOT) and round 11 extends its
fake git with probe ANSWERS (thread 3833880596's fork-point probes)
and remote-mutation argv (thread 3833880605's pr-guard-canonical
repair). Everything a TEST imports by name lives here now; the
harness re-exports the same names so the existing suites' imports
keep working, and stays the home of the MergeHarness runner itself.
Like the harness, this is a PLAIN module (thread 3832660856):
importing it adds nothing to unittest discovery.
"""

from datetime import datetime, timezone

from .pr_guard_classify import Thread
from .pr_guard_dequeue import DEQUEUE_MUTATION, QUEUE_ENTRY_QUERY
from .pr_guard_common import GUARD_GPGSIGN_FALSE
from .pr_guard_common import GUARD_USER_EMAIL, GUARD_USER_NAME
from .pr_guard_common import POLL_FIELDS

# Thread 3835345690 (PR #41 round 27): the identity flags every
# expected revert argv carries between `git -C <tmp>` and `revert` —
# imported from pr_guard_common so the fixtures track the
# implementation's single source of truth (the round-27 suite pins
# the literal values independently).
GUARD_ID = (
    f"-c user.name={GUARD_USER_NAME} -c user.email={GUARD_USER_EMAIL}"
)
# Thread 3835379480 (PR #41 round 28): the config half of the
# unsigned pinning beside the identity — the flag half
# (--no-gpg-sign) rides the subcommand in the expected argvs below —
# so a signing-forcing checkout (commit.gpgSign=true, no usable key)
# cannot fail the revert commit.
GUARD_NO_SIGN = f"-c {GUARD_GPGSIGN_FALSE}"

HEAD = "b979176095b9dd6b6f8e989ed460feab9ce0abc4"
MERGE_SHA = "2e50a4211c0d7a2b3b0a99ff64d13e5b7a901234"
REVERT_PR_URL = "https://github.com/RachaelsDen/UR-lorebook/pull/41\n"
# Thread 3833073952 (PR #41): every gh pr argv is pinned with the repo
# flag, so the expected-argv strings carry it too — any exact-sequence
# assertion doubles as a pinning assertion.
REPO_FLAG = "-R RachaelsDen/UR-lorebook"
MERGE_ARGV = (
    f"gh pr merge 39 --merge --match-head-commit {HEAD} {REPO_FLAG}"
)
# Thread 3836501981 (PR #45 round 15): the poll argv renders
# POLL_FIELDS itself (updatedAt joined the field list then; thread
# 3836600782, round 17, retired the corroboration with it) — one
# source of truth with the reads.
POLL_ARGV = f"gh pr view 39 --json {POLL_FIELDS} {REPO_FLAG}"
HEAD_ARGV = f"gh pr view 39 --json headRefOid {REPO_FLAG}"
# Thread 3835145981 (PR #41 round 25): the PRE-DISPATCH commit-list
# snapshot read — taken beside HEAD_ARGV before the merge dispatch
# and frozen for every later revert path.
SNAPSHOT_ARGV = (
    f"gh api --method GET repos/RachaelsDen/UR-lorebook/pulls/39"
    "/commits?per_page=100&page=1"
)
# Thread 3833073940 (PR #41): the queue-entry probe argvs (GraphQL
# mergeQueueEntry, plus the REST mergeable_state corroboration read
# that runs only when GraphQL is unreadable).
GRAPHQL_ARGV = (
    f"gh api graphql -f query={QUEUE_ENTRY_QUERY} "
    f"-F owner=RachaelsDen -F name=UR-lorebook -F number=39"
)
REST_PR_ARGV = "gh api repos/RachaelsDen/UR-lorebook/pulls/39"
# Thread 3834375737 (PR #41 round 15): the dequeue argvs — the PR's
# node id rides the existing pinned PR view, and the mutation is its
# own graphql call (distinct from the queue-entry probe above).
PR_NODE_ID = "PR_kwLOURLOREtest39node0000000001"
NODE_ID_ARGV = f"gh pr view 39 --json id {REPO_FLAG}"
DEQUEUE_ARGV = (
    f"gh api graphql -f query={DEQUEUE_MUTATION} -f id={PR_NODE_ID}"
)
# Thread 3833762325 (PR #41 round 10): the default `git remote -v`
# listing — an ordinary canonical checkout whose origin IS
# RachaelsDen/UR-lorebook. Fork-checkout scenarios override remote_v.
CANONICAL_REMOTE_V = "origin\tgit@github.com:RachaelsDen/UR-lorebook.git (fetch)\norigin\tgit@github.com:RachaelsDen/UR-lorebook.git (push)\n"
# Thread 3834400954 (PR #41 round 16): the head of the revert commit
# the fake worktree reports for `git -C <tmp> rev-parse HEAD` — a
# reuse fixture points remote_heads at exactly this sha.
REVERT_HEAD = "aaaa00000000000000000000000000000000000e1"
# Thread 3834488871 (PR #41 round 16): the placeholder worktree path
# for revert_argv when no captured tmp is supplied.
WORKTREE_TMP = "<tmp>"
# Thread 3833880596 (PR #41 round 11), replaced by thread 3834093635
# (round 13): the landing-shape fixture constants — the PR head REF
# the fork-point probe reads and the well-known FORK sha it serves.
# (The round-11 parent sha and the round-12 reachability probe left
# with the discriminator they served.)
PR_HEAD_REF = "refs/pull/39/head"
FORK_SHA = "ffff000000000000000000000000000000000066"
# Thread 3835145981 (PR #41 round 25): the round-25 two-case contract
# probes the landing's PARENT and the current BASE TIP — these two
# shas answer those probes, and the DEFAULTS are EQUAL (the automated
# single-parent shape: parent IS the current <remote>/<base> tip, so
# the plain `git revert --no-edit <merge_sha>` runs); a fail-closed
# fixture overrides landing_parent to a DIFFERENT sha.
BASE_TIP = "1111000000000000000000000000000000000aa"
LANDING_PARENT = BASE_TIP
# A parent sha that is NOT the base tip — the fail-closed default for
# tests that pass landing_parent directly.
FOREIGN_PARENT = "2222000000000000000000000000000000000bb"


# Thread 3834590319 (PR #41 round 17): an int OR a per-call LIST of
# dequeue-mutation exit codes (the last repeats forever) — the retry
# scenarios need fail-then-succeed outcomes across attempts.
def rc_sequence(values):
    seq = list(values) if isinstance(values, (list, tuple)) else [values]

    def take() -> int:
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return take


# Thread 3835846318 (PR #45 round 3): the WALL-CLOCK base the fake
# time() serves — merge_guarded captures the dispatch timestamp from
# the (faked) clock right before `gh pr merge` leaves, and the
# landing identity gate compares a reconciled landing's committer
# date against it; date fixtures pick ct values on either side.
WALL_NOW = 1_700_000_000.0


# Thread 3836501981 -> 3836565818 (PR #45 rounds 15-16): an
# ISO-8601 `updatedAt` stamp relative to WALL_NOW — the shape gh
# pr view serves, for the landing-corroboration fixtures
# (pending()/merged() stamp their records an hour apart so the
# ordinary fresh transitions corroborate — round 16's same-clock
# rule needs only the landing's advancement past the baseline's
# own; ambiguity fixtures serve equal or unreadable stamps).
def iso_at(offset_secs: float) -> str:
    return datetime.fromtimestamp(
        WALL_NOW + offset_secs, tz=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeClock:
    """Thread 3832522300's fake clock: monotonic() advances only via
    sleep(), so deadline arithmetic asserts in exact fake seconds.
    Thread 3835846318 (PR #45 round 3): time() serves the fixed
    WALL_NOW wall clock — the dispatch timestamp source. Thread
    3836217630 (PR #45 round 10): the WALL clock advances with
    sleep() too (starting at WALL_NOW, still the dispatch moment —
    no sleep precedes the dispatch), because the round-10 live-
    baseline rule date-checks each poll read against the dispatch
    wall clock (only reads >= MERGE_POLL_INTERVAL past it credit);
    a fixed time() would freeze every read inside the first
    interval."""

    def __init__(self):
        self.now, self.slept = 0.0, []
        self.wall = WALL_NOW

    def monotonic(self):
        return self.now

    def time(self):
        return self.wall

    def sleep(self, secs):
        self.slept.append(secs)
        self.now += secs
        self.wall += secs


def thread(label: str, classification: str) -> Thread:
    record = Thread(
        node_id=f"PRRT_{label}",
        head_id=int(label),
        last_id=int(label) + 1,
        last_author="RachaelsDen",
        last_author_type="User",
        last_body="...",
        is_resolved=classification == "resolved",
        is_outdated=False,
    )
    record.classification = classification
    return record


def merged(base: str = "dev", head: str = HEAD) -> dict:
    return {"state": "MERGED", "mergeCommit": {"oid": MERGE_SHA},
            "baseRefName": base, "headRefOid": head,
            "updatedAt": iso_at(3600.0)}


def pending(base: str = "dev") -> dict:
    return {"state": "OPEN", "mergeCommit": None,
            "baseRefName": base, "headRefOid": HEAD,
            "updatedAt": iso_at(-3600.0)}


# Thread 3834488871/3834400954 (PR #41 round 16) rework, widened by
# thread 3834819191 (round 20): the revert sequence builds the commit
# in a THROWAWAY WORKTREE (the base fetch stays repo-level in the
# caller checkout), consults ls-remote before the push, and removes
# the worktree after the PR create. NO branch is ever checked out —
# the worktree stays DETACHED and the push lands the commit directly
# as HEAD:refs/heads/<name> (a caller-active branch name can never
# block the build). `tmp` defaults to the placeholder — exact-sequence
# assertions pass the harness-captured RUNNER.revert_tmp.
def revert_argv(
    base: str, tmp: str = WORKTREE_TMP, single_parent: bool = False
) -> list[str]:
    branch = f"revert/pr39-{MERGE_SHA[:7]}"
    # Thread 3835145981/3835175506/08 (round 25): the single-parent
    # plan probes the landing's PARENT and the CURRENT base tip
    # (caller-side, after the pre-revert base fetch) before the plain
    # revert — the two-case contract's only single-parent automated
    # shape is parent == <remote>/<base>.
    probes = (
        [
            f"git rev-parse --verify {MERGE_SHA}^",
            f"git rev-parse --verify origin/{base}",
        ]
        if single_parent
        else []
    )
    # Threads 3835345690 (round 27) + 3835379480 (round 28): both
    # revert shapes carry the fixed guard identity AND the unsigned
    # pinning — an automation checkout without user.name/user.email
    # must still get its revert commit, and one with
    # commit.gpgSign=true but no usable signing key must not fail
    # building a signature for it.
    revert = (
        f"{GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign "
        f"--no-edit {MERGE_SHA}"
        if single_parent
        else (
            f"{GUARD_ID} {GUARD_NO_SIGN} revert --no-gpg-sign "
            f"-m 1 --no-edit {MERGE_SHA}"
        )
    )
    return [
        # Thread 3833762325: the canonical-remote resolution precedes
        # every git step of the revert (fetch/checkout/push all use
        # the resolved name — origin in the default canonical env).
        "git remote -v",
        f"git fetch origin {base}",
        f"git worktree add --detach {tmp} origin/{base}",
        # Thread 3833540921: the parent-count probe between the
        # worktree and the revert decides the argv shape.
        f"git -C {tmp} rev-parse --verify {MERGE_SHA}^2",
        *probes,
        f"git -C {tmp} {revert}",
        # Thread 3834400954: the local revert head + the remote
        # branch head decide reuse/suffix before the push.
        f"git -C {tmp} rev-parse HEAD",
        "git ls-remote origin refs/heads/" + branch,
        # Thread 3834819191: the push creates the remote branch from
        # the DETACHED worktree HEAD directly — no local branch.
        f"git -C {tmp} push origin HEAD:refs/heads/{branch}",
        f"gh pr create --base {base} --head {branch}",
        f"git worktree remove --force {tmp}",
    ]


def queued_entry() -> dict:
    return {"state": "QUEUED"}


# Thread 3834883632 (PR #41 round 21): serve ONE page of the
# paginated PR commit-list read — REST repos/<owner>/<repo>/pulls/
# <n>/commits?per_page=100&page=<k>, the exact entry shape
# read_pr_commits consumes — cut from oids in per_page=100 chunks;
# a SHORT page (<100) is what stops the implementation's page
# cursor, so a >100-oid fixture exercises the second GET.
def commits_page(argv: list[str], oids: list[str]) -> list[dict]:
    page = int(argv[-1].split("page=")[-1])
    chunk = oids[(page - 1) * 100 : page * 100]
    return [{"sha": oid} for oid in chunk]


# Thread 3834093635 (round 13), refit at round 25 (threads
# 3835145976/3835145981/3835175506/3835175508): the git_answers
# fixture for the FAIL-CLOSED banner's DIAGNOSTIC probes — a callable
# the harness consults BEFORE its built-in git handlers, receiving
# the argv AND the stdin text of the call. The classifier and its
# patch-id/delta plumbing are RETIRED; what remains is: the
# fork-point probe `git merge-base refs/pull/<n>/head <base_ref>`
# serves `fork`; the range-list probe `git rev-list --no-merges
# <fork>..<landing>` serves `range_shas` (a NEWEST-first list, real
# rev-list order — `landed` (a count) synthesizes foreign advancement
# shas + merge_sha); and the subject probe `git log --no-walk` serves
# `commit_meta` rows (sha -> "author <email>|subject") for the
# MARKER-presence diagnostic — a subject ending " (#<digits>)" is a
# marker, user-controlled text that licenses nothing (thread
# 3835145976). fork_rc/list_rc/log_rc make the corresponding probe
# UNREADABLE (the banner then reports the degradation). Unmatched
# argv return None and fall through to the harness defaults.
def landing_probes(
    merge_sha: str,
    fork: str = FORK_SHA,
    landed: int = 1,
    range_shas: list[str] | None = None,
    base_ref: str = "origin/dev",
    pr: int = 39,
    fork_rc: int = 0,
    list_rc: int = 0,
    # sha -> "author <email>|subject" for the marker diagnostic's
    # `git log --no-walk` call — the DEFAULT gives every sha the SAME
    # marker-free subject; a row ending "|<subject> (#<digits>)"
    # reports a marker in the banner.
    commit_meta: dict[str, str] | None = None,
    log_rc: int = 0,
):
    if range_shas is None:
        foreign = [
            f"eeee0000000000000000000000000000000000{i:02d}"
            for i in range(landed - 1)
        ]
        range_shas = foreign + [merge_sha]
    meta_table = dict(commit_meta or {})
    default_meta = "Queue Bot <queue-bot@example.invalid>|queued change"

    def answer(argv, stdin):
        if (
            argv[:2] == ["git", "merge-base"]
            and argv[2:4] == [f"refs/pull/{pr}/head", base_ref]
        ):
            return (fork_rc, fork + "\n" if fork_rc == 0 else "")
        if argv[:3] == ["git", "rev-list", "--no-merges"] and len(
            argv
        ) == 4 and argv[3] == f"{fork}..{merge_sha}":
            if list_rc != 0:
                return (list_rc, "")
            # Newest-first — exactly what a real rev-list of this
            # range prints (the landing first).
            return (0, "\n".join(reversed(range_shas)) + "\n")
        if argv[:2] == ["git", "log"] and "--no-walk" in argv:
            if log_rc != 0:
                return (log_rc, "")
            named = argv[
                next(
                    i for i, a in enumerate(argv)
                    if a.startswith("--format=")
                ) + 1:
            ]
            return (
                0,
                "".join(
                    f"{sha}|{meta_table.get(sha, default_meta)}\n"
                    for sha in named
                ),
            )
        return None

    return answer
