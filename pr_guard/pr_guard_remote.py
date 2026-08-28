"""The canonical-remote resolution for every git operation in the
revert path.

Split from pr_guard_range.py at the PR #41 round-11 fixes (thread
3833880605): the round-10 resolver (thread 3833762325) scanned `git
remote -v` for a FETCH url CONTAINING the slug — two fresh holes. A
TRIANGULAR remote (fetch = canonical repository, pushurl = the
contributor's fork — the normal fork-contribution setup) was selected
by its fetch line, and the later `git push <remote>` follows the
PUSH URL, landing the revert branch on the fork while every survey
and gh pr command targeted RachaelsDen/UR-lorebook. And the substring
test accepted similarly named repositories such as
RachaelsDen/UR-lorebook-backup as "canonical".

The resolver now parses BOTH endpoints of every remote (the `(fetch)`
and `(push)` lines of `git remote -v`) and requires the EXACT
repository path on each: the URL's trailing OWNER/REPO (after
stripping an optional `.git` suffix and trailing slash, with the scp
colon normalized) must EQUAL RachaelsDen/UR-lorebook. A remote whose
endpoints both qualify is used by name. A TRIANGULAR remote (exact
canonical fetch, non-canonical push) is repaired instead of used: the
dedicated remote `pr-guard-canonical` is added (or set-url-repaired)
pointing BOTH directions at the canonical FETCH URL — the credential
that already authenticates fetches from the canonical repository;
if that credential cannot push, the push step fails loudly and the
manual banner covers it. When the dedicated remote cannot be
created, or no remote fetches canonically at all, resolution fails
closed with setup instructions and the caller blocks the revert
(never a silent push to the fork).

Thread 3833993106 (PR #41 round 12): the exact-PATH parser still
discarded the HOST — git@mirror.example:RachaelsDen/UR-lorebook.git
and even a local path ending in the same two segments qualified, and
the revert would fetch and push through the mirror while the pinned
gh pr create still targets github.com, so the revert branch might
not exist in the canonical repository at all. The parser now
requires the URL to BE a GitHub URL: the host must be LITERALLY
github.com — the scp form git@github.com:<slug>, the ssh:// form, or
https://github.com/<slug>, with exactly the two slug segments as the
path. SSH host ALIASES (gh:<slug>) are hard-blocked with expansion
instructions rather than resolved through git config, so no alias
can silently redirect the canonical traffic.

Thread 3834210476 (PR #41 round 14): a remote may hold SEVERAL URLs
per endpoint — `git remote -v` emits one (fetch)/(push) line per
configured URL (multiple fetch URLs via `git remote set-url --add`,
multiple pushurls via `--push --add`), and `git push <remote>` tries
the configured push URLs — but the round-13 resolver kept only the
LAST line per endpoint, so a remote holding a fork pushurl BESIDE
the canonical one validated clean while the revert branch could
still land on the fork (or the push could die on an unavailable
earlier URL before ever reaching the canonical one, leaving no
branch for the pinned `gh pr create`). Every endpoint's URL LIST
must be non-empty and ALL-canonical now. Repairing a mis-pointed
dedicated remote REBUILDS it (`git remote remove` + `git remote
add`) — `git remote set-url --push` replaces only the FIRST pushurl
and leaves every extra one configured, which is exactly the stray
this round closes; the remove+add leaves one fetch URL and no
pushurls, so nothing stray survives by construction.
"""

import subprocess

from .pr_guard_common import REPO_SLUG

# Thread 3833993106 (PR #41 round 12): the canonical GitHub host. A
# URL naming the slug on any OTHER host — a mirror, a local path, an
# SSH host alias — is not the repository this guard's -R-pinned gh
# commands target.
GITHUB_HOST = "github.com"

# Thread 3833880605 (PR #41 round 11): the dedicated remote installed
# when the checkout's canonical-fetching remote pushes elsewhere. A
# fixed, self-describing name — if it already exists with EVERY
# endpoint URL canonical it is simply used (the both-endpoints loop
# finds it first); if it exists mis-pointed (any stray URL, thread
# 3834210476), the remove+add rebuild realigns it.
GUARD_REMOTE = "pr-guard-canonical"


# Thread 3833880605 (round 11) + thread 3833993106 (round 12):
# exact-repository test for ONE remote URL. Round 11 parsed the URL's
# final OWNER/REPO path segments (scp colon normalized, optional .git
# suffix and trailing slash stripped) and required them to EQUAL the
# canonical slug — but discarded the HOST, so
# git@mirror.example:RachaelsDen/UR-lorebook.git and a local path
# ending in the same two segments qualified. The URL must now parse
# as a GITHUB URL: the host must be LITERALLY github.com — the scp
# form git@github.com:<slug>, ssh://git@github.com/<slug>, or
# https://github.com/<slug>. http://, git://, file://, any other
# host, any host:port form, and any URL whose path is not exactly
# the two slug segments do not. An SSH host ALIAS (gh:<slug>) is
# rejected outright — the fail-closed banner carries the expansion
# instructions instead of resolving the alias through git config.
def url_is_canonical(url: str) -> bool:
    cleaned = url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    if "://" in cleaned:
        scheme, _, rest = cleaned.partition("://")
        if scheme not in ("ssh", "https"):
            return False
        authority, _, path = rest.partition("/")
    else:
        # The scp-like form has no slash before its colon; anything
        # else (an absolute or relative local path) is not a URL.
        authority, colon, path = cleaned.partition(":")
        if not colon or "/" in authority:
            return False
    host = authority.rpartition("@")[2]
    parts = [p for p in path.split("/") if p]
    return (
        host == GITHUB_HOST
        and len(parts) == 2
        and "/".join(parts) == REPO_SLUG
    )


# Thread 3833880605 (round 11), widened by thread 3834210476 (round
# 14): the resolved canonical remote NAME for `git fetch <remote>` /
# `git push <remote>`, or "" after printing the fail-closed banner.
# A remote qualifies ONLY when EVERY fetch URL AND EVERY push URL
# name RachaelsDen/UR-lorebook exactly — `git remote -v` emits ONE
# line per configured URL (multi fetch-urls and multi pushurls both
# exist in git), and `git push <remote>` follows the PUSH URLs, so a
# triangular remote (any canonical fetch, any non-canonical push —
# including a fork pushurl sitting BESIDE a canonical one) must never
# be used as-is.
def canonical_remote() -> str:
    ends: dict[str, dict[str, list[str]]] = {}
    proc = subprocess.run(
        ["git", "remote", "-v"], capture_output=True, text=True
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 3 and fields[-1] in ("(fetch)", "(push)"):
                ends.setdefault(fields[0], {}).setdefault(
                    fields[-1][1:-1], []
                ).append(fields[1])
    for name, urls in ends.items():
        if endpoints_canonical(urls):
            return name
    for name, urls in ends.items():
        if fetches_canonical(urls) and not endpoints_canonical(urls):
            return repair_triangular_remote(name, urls)
    print(
        f"NO CANONICAL REMOTE: `git remote -v` lists no remote whose "
        f"EVERY fetch and push URL is a GITHUB URL naming {REPO_SLUG} "
        f"exactly — host literally {GITHUB_HOST}: "
        f"git@{GITHUB_HOST}:{REPO_SLUG}.git or "
        f"https://{GITHUB_HOST}/{REPO_SLUG}.git (threads "
        f"3833762325/3833880605/3833993106/3834210476). A MIRROR host "
        f"(git@mirror.example:{REPO_SLUG}.git), a local path, an SSH "
        f"host ALIAS, or a STRAY second pushurl beside the canonical "
        f"one does not qualify — the revert would fetch and push "
        f"through that remote while every pinned gh command targets "
        f"{GITHUB_HOST}. Expand the alias to its real github.com URL "
        f"(git config --get-urlmatch, then git remote set-url), or "
        f"add a canonical remote (git remote add upstream "
        f"https://{GITHUB_HOST}/{REPO_SLUG}.git) and re-run."
    )
    return ""


# Thread 3834210476 (PR #41 round 14): qualification helpers over the
# MULTI-VALUED endpoint lists. An endpoint qualifies only when its
# URL list is NON-EMPTY and EVERY URL passes url_is_canonical — the
# round-13 dict kept one URL per endpoint and validated only the
# LAST push line, missing a stray pushurl entirely.
def endpoints_canonical(urls: dict[str, list[str]]) -> bool:
    for kind in ("fetch", "push"):
        listed = urls.get(kind) or []
        if not listed or not all(url_is_canonical(u) for u in listed):
            return False
    return True


def fetches_canonical(urls: dict[str, list[str]]) -> bool:
    listed = urls.get("fetch") or []
    return bool(listed) and all(url_is_canonical(u) for u in listed)


# Thread 3833880605: the triangular shape — the remote FETCHES the
# canonical repository (every fetch URL canonical) but a push URL
# targets elsewhere (a fork pushurl, a mirror, or a stray second
# pushurl beside the canonical one), so `git push <remote>` would
# land the revert branch outside the canonical repository. The
# dedicated GUARD_REMOTE is installed at the canonical FETCH URL (the
# credential already trusted for canonical traffic) and every
# fetch/push of the revert goes through it. An add or repair that
# fails leaves the hard block — never a push to a stray URL.
def repair_triangular_remote(
    name: str, urls: dict[str, list[str]]
) -> str:
    url = urls["fetch"][0]
    stray = ", ".join(urls.get("push") or [])
    added = subprocess.run(
        ["git", "remote", "add", GUARD_REMOTE, url]
    ).returncode
    if added != 0:
        # Thread 3834210476 (PR #41 round 14): the add fails when the
        # dedicated remote ALREADY exists, and a set-url repair is the
        # exact bug it would fix — `git remote set-url --push` replaces
        # only the FIRST pushurl, leaving every extra pushurl
        # configured to carry the revert branch to the stray
        # destination. Rebuild instead: remove the remote entirely,
        # then add it back at the one canonical URL — the add leaves
        # exactly ONE fetch URL and NO pushurls, so nothing stray
        # survives by construction.
        removed = subprocess.run(
            ["git", "remote", "remove", GUARD_REMOTE]
        ).returncode
        readded = subprocess.run(
            ["git", "remote", "add", GUARD_REMOTE, url]
        ).returncode
        if removed != 0 or readded != 0:
            print(
                f"REVERT BLOCKED: remote '{name}' fetches {REPO_SLUG} "
                f"but its PUSH URL(S) ({stray}) are not all canonical "
                f"github.com URLs — `git push {name}` would follow a "
                f"stray pushurl and land the revert branch OUTSIDE the "
                f"canonical repository (threads 3833880605/3834210476), "
                f"and rebuilding the dedicated remote '{GUARD_REMOTE}' "
                f"at {url} failed (git remote remove + git remote add). "
                f"Fix the pushurls (git remote remove {name} + git "
                f"remote add {name} <canonical-url>, or delete the "
                f"stray: git remote set-url --push --delete {name} "
                f"<stray-url>) and re-run; the merge MUST be reverted "
                f"manually meanwhile (direct pushes are "
                f"ruleset-blocked; revert via PR)."
            )
            return ""
    print(
        f"CANONICAL PUSH REPAIRED (threads 3833880605/3834210476): "
        f"remote '{name}' fetches {REPO_SLUG} but its PUSH URL(S) "
        f"({stray}) are not all canonical — `git push {name}` would "
        f"follow a stray pushurl and carry the revert branch outside "
        f"the canonical repository — so the dedicated remote "
        f"'{GUARD_REMOTE}' ({url}, fetch AND push) now carries every "
        f"git operation of this revert."
    )
    return GUARD_REMOTE
