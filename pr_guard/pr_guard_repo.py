"""The repository-target resolution for the extracted toolkit.

The pr_guard family was born inside the UR-lorebook repository (the
.omo/start-work lineage, PRs #36-#49 — the 33-round hardened
in-repo tool this package was extracted from), where every module
hardcoded REPO_OWNER/REPO_NAME = RachaelsDen/UR-lorebook in
pr_guard_common. This module owns the standalone toolkit's
replacement: a resolution chain (the --repo flag -> the PR_GUARD_REPO
env var -> the CWD's `git remote get-url origin`), and configure() —
the ONE setter that rebinds the repo-derived names in
pr_guard_common AND in every already-imported package module.

WHY THE WALK (the from-import trap): the family's modules bind
REPO_OWNER/REPO_NAME/REPO_SLUG/REPO_FLAG/RECEIPT_AUTHORS with
`from pr_guard_common import ...` — Python binds the VALUE at
import time, so rebinding the names in pr_guard_common alone would
leave every early-bound copy stale and the guard could survey one
repository while merging another (exactly the split-brain class the
-R pinning of thread 3833073952 exists to prevent). configure()
therefore walks sys.modules and rebinds all five names in every
pr_guard.* module that holds them; modules imported LATER bind the
already-configured values from pr_guard_common directly.

THE IMPORT-TIME DEFAULTS ARE THE HISTORIC FIXTURE: pr_guard_common
still carries RachaelsDen/UR-lorebook as its import-time values.
That is deliberate, not an oversight: the 596-test suite (the
family's hardening record) bakes the fixture into module-level
constants at import time (DISABLE_ARGV, CANCEL_ARGV, REPO_ROOT —
f-strings evaluated when the test modules load), and unittest
DISCOVERY imports sibling suites alphabetically BEFORE any
load_tests hook could configure anything, so only import-time
values keep both loader routes (aggregate == discovery) exactly
once and exactly green. The CLI never relies on the fixture: the
process entries (pr_guard.cli.run — the console script,
`python -m pr_guard`, and the release zipapp) resolve the target
BEFORE any mode dispatch and REFUSE to run (exit 2) when nothing
resolves; the aggregator's load_tests pins the fixture explicitly
before loading the suites.

The origin-remote parser mirrors pr_guard_remote's GitHub-URL
doctrine (threads 3833880605/3833993106): only the scp form
git@github.com:<slug>, ssh://git@github.com/<slug>, or
https://github.com/<slug> (each with an optional .git suffix and
trailing slash) resolves — a slug on any OTHER host (a mirror, a
GHE instance, an SSH alias) would configure a repository the
family's GH_HOST-pinned gh subprocesses can never reach, so it
resolves NOTHING and the caller reports the clean usage error.
"""

import os
import subprocess
import sys

from . import pr_guard_common as common

# The env var consulted between the --repo flag and the origin
# remote: PR_GUARD_REPO=OWNER/NAME.
REPO_ENV = "PR_GUARD_REPO"

# The canonical GitHub host for origin detection — the same host
# every gh subprocess in the family is pinned to (GH_HOST_PIN,
# thread 3834400946).
GITHUB_HOST = "github.com"

# The five repo-derived bindings pr_guard_common owns and the
# family from-imports — everything configure() must keep coherent.
_REPO_BINDINGS = (
    "REPO_OWNER",
    "REPO_NAME",
    "REPO_SLUG",
    "REPO_FLAG",
    "RECEIPT_AUTHORS",
)

# Set by configure(): once the target has been resolved explicitly
# (flag, env, origin remote, or the test-fixture pin), the process
# entry points need not resolve again.
_configured = False


def repo_configured() -> bool:
    return _configured


# OWNER/NAME — exactly one slash, both segments non-empty, no
# whitespace (GitHub owner and repository names never carry it).
def parse_repo_slug(text: str) -> tuple[str, str] | None:
    parts = text.strip().split("/")
    if (
        len(parts) == 2
        and all(parts)
        and not any(ch.isspace() for part in parts for ch in part)
    ):
        return parts[0], parts[1]
    return None


# The --repo flag's value from a raw argv — None when the flag is
# absent, "" when it appears with no value at all (the caller's
# validation reports the usage error).
def repo_flag_value(argv: list[str]) -> str | None:
    if argv[1:2] == ["--repo"]:
        return argv[2] if len(argv) > 2 else ""
    return None


# One origin-remote URL -> (owner, name), or None when the URL does
# not name a github.com OWNER/NAME repository (see the module
# docstring's host doctrine). Optional trailing slash and .git
# suffix are stripped before the path is read.
def parse_origin_url(url: str) -> tuple[str, str] | None:
    cleaned = url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    if "://" in cleaned:
        scheme, _, rest = cleaned.partition("://")
        if scheme not in ("ssh", "https"):
            return None
        authority, _, path = rest.partition("/")
    else:
        # The scp-like form has no slash before its colon; anything
        # else (an absolute or relative local path) is not a URL.
        authority, colon, path = cleaned.partition(":")
        if not colon or "/" in authority:
            return None
    if authority.rpartition("@")[2] != GITHUB_HOST:
        return None
    parts = [p for p in path.split("/") if p]
    if len(parts) != 2:
        return None
    return parse_repo_slug("/".join(parts))


# The CWD's origin remote URL — "" on any failure (no repository,
# no origin, no git): an unresolvable CWD is the chain's TERMINAL
# fallback, never an error in itself.
def origin_remote_url() -> str:
    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


# The ONE setter. Rebinds the five repo-derived names in
# pr_guard_common (the source of truth every later import binds)
# and walks sys.modules so every ALREADY-imported pr_guard module's
# early-bound copies follow (the from-import trap in the module
# docstring). The walk rebinds a module binding ONLY when it is the
# IDENTICAL object pr_guard_common held before the call — a genuine
# `from pr_guard_common import ...` binds exactly that object,
# while a same-NAMED local constant (pr_guard_merge_fixtures'
# string REPO_FLAG, a different constant the harness joins into its
# fake argv strings) is a different object and stays untouched.
# Idempotent; call it as many times as resolution demands.
def configure(owner: str, name: str) -> None:
    global _configured
    stale = {binding: getattr(common, binding, None) for binding in _REPO_BINDINGS}
    common.REPO_OWNER = owner
    common.REPO_NAME = name
    common.REPO_SLUG = f"{owner}/{name}"
    common.REPO_FLAG = ["-R", common.REPO_SLUG]
    common.RECEIPT_AUTHORS = frozenset({owner})
    _configured = True
    fresh = {binding: getattr(common, binding) for binding in _REPO_BINDINGS}
    for module in list(sys.modules.values()):
        mod_name = getattr(module, "__name__", "")
        if mod_name != __package__ and not mod_name.startswith(
            __package__ + "."
        ):
            continue
        for binding, old_value in stale.items():
            if vars(module).get(binding) is old_value:
                setattr(module, binding, fresh[binding])


# The process-entry resolution chain: the explicit --repo flag,
# else PR_GUARD_REPO, else the CWD's origin remote. Each supplied
# source must PARSE (a malformed flag or env value is a usage
# error, never a silent fall-through to a weaker source); nothing
# resolving is the terminal clean usage error (die exits 2).
def resolve_repo_target(explicit: str | None) -> tuple[str, str]:
    if explicit is not None:
        parsed = parse_repo_slug(explicit) if explicit else None
        if parsed is not None:
            return parsed
        common.die(
            f"--repo {explicit!r} is not OWNER/NAME — pass the "
            f"target as '--repo owner/name' (one slash, no spaces)"
        )
    env_value = os.environ.get(REPO_ENV, "").strip()
    if env_value:
        parsed = parse_repo_slug(env_value)
        if parsed is not None:
            return parsed
        common.die(
            f"{REPO_ENV}={env_value!r} is not OWNER/NAME — set it "
            f"to 'owner/name' or unset it"
        )
    url = origin_remote_url()
    parsed = parse_origin_url(url) if url else None
    if parsed is not None:
        return parsed
    common.die(
        "no repository target: pass --repo OWNER/NAME or set "
        f"{REPO_ENV} (neither was given and the CWD's 'git remote "
        "get-url origin' did not resolve to a github.com "
        "OWNER/NAME repository)"
    )
