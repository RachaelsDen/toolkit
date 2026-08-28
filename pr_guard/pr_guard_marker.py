"""The squash-MARKER diagnostic probe (PR #41, retired to diagnostics
at round 25).

Born at the round-24 fixes (threads 3835052616/3835052612) as the
FINAL provenance discriminator — GitHub's default squash subject ends
" (#<N>)" while a rebase tip replays ORIGINAL subjects — and RETIRED
one round later by thread 3835145976: a rebase tip's ORIGINAL subject
can ITSELF end in "(#<this PR>)" (an issue reference, or a subject
amended after the PR number became known), so the marker is
USER-CONTROLLED COMMIT TEXT, not GitHub-owned landing metadata, and
can corroborate nothing. The marker probes survive round 25 in exactly
one role: the fail-closed banner (pr_guard_range) reports the landing
tip's trailing marker as a DIAGNOSTIC to help the human decide — no
marker reading licenses or blocks anything anymore.

probe_commit_meta moved here from pr_guard_patch_id when that module
died with the classifier (round 25): marker_table needs subjects, and
the batched `git log --no-walk` probe is the only metadata reader
left. Imports flow ONE way (range -> marker; subprocess only below).
"""

import subprocess


# Thread 3834819188 (round 20, moved from pr_guard_patch_id at round
# 25): sha list -> {sha: "author <email>|subject"}, ONE batched
# `git log --no-walk --format=%H|%an <%ae>|%s` over every fed oid (the
# per-commit form is one subprocess each; --no-walk shows EXACTLY the
# named commits without traversing ancestry, and the leading %H keys
# each record because --no-walk's output order is not the feeding
# order). A commit whose subject contains "|" still parses
# deterministically — the FIRST "|" splits off the 40-hex sha and the
# consumer only needs the subject tail. Returns None on a nonzero exit
# so the caller's diagnostics report the probe UNREADABLE (an
# UNREADABLE metadata map must never read as "no markers").
def probe_commit_meta(shas: list[str]) -> dict[str, str] | None:
    if not shas:
        return {}
    logged = subprocess.run(
        ["git", "log", "--no-walk", "--format=%H|%an <%ae>|%s", *shas],
        capture_output=True,
        text=True,
    )
    if logged.returncode != 0:
        return None
    meta: dict[str, str] = {}
    for line in logged.stdout.splitlines():
        head, sep, rest = line.partition("|")
        if sep and head:
            meta[head] = rest
    return meta


# Thread 3835052616 (round 24): the trailing "(#<digits>)" SQUASH
# MARKER of a subject — GitHub's default squash subject is "<PR
# title> (#<N>)", and the marker is the LAST parenthesized run, so
# only a subject ENDING in the marker counts ("fix (#12) (#34)"
# carries #34, "fix (#12) only" carries none). Returns the digits,
# "" when the subject carries no trailing marker. Round 25 (thread
# 3835145976): the digits are the subject's own text — a user may end
# ANY commit's subject in "(#N)" — so the return value is diagnostic
# input only.
def squash_marker(subject: str) -> str:
    if not subject.endswith(")"):
        return ""
    opens = subject.rfind(" (#")
    if opens == -1:
        return ""
    digits = subject[opens + 3 : -1]
    return digits if digits.isdigit() else ""


# Thread 3835052616 (round 24): the per-sha marker table — {sha:
# digits} for every fed sha whose subject ends in a squash marker,
# {} when none does. None when the metadata probe is UNREADABLE or
# omits a fed sha: the fail-closed banner reports that as "marker
# probe unreadable", never as "no markers".
def marker_table(shas: list[str]) -> dict[str, str] | None:
    meta = probe_commit_meta(shas)
    if meta is None or any(sha not in meta for sha in shas):
        return None
    marked = {
        sha: squash_marker(meta[sha].partition("|")[2])
        for sha in shas
    }
    return {sha: digits for sha, digits in marked.items() if digits}
