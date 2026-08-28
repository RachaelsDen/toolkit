# pr-guard

A review-loop guard for GitHub pull requests reviewed by a codex-style
review bot (e.g. `chatgpt-codex-connector[bot]`). It closes the gap
between "the bot looked at the PR" and "every finding was answered by a
human": review-thread state — never vibes, never a bare green check — is
the merge authority, and the merge request itself is dispatched in the
same process as the final thread survey.

Pure Python standard library. Requires Python >= 3.10 and the `gh` CLI
(authenticated) for live operation.

## Install

From a release wheel with [pipx](https://pipx.pypa.io/) (adjust the
owner once the repository is public):

```sh
pipx install https://github.com/<owner>/pr-guard/releases/download/v0.1.0/pr_guard-0.1.0-py3-none-any.whl
```

Copy-and-run single file: grab `pr-guard.pyz` from the release assets,
then run it anywhere with a Python 3.10+ interpreter — directly
executable (env shebang) or through the interpreter:

```sh
./pr-guard.pyz survey 49          # or: python3 pr-guard.pyz survey 49
```

From git:

```sh
pipx install git+https://github.com/<owner>/pr-guard.git
```

In a checkout, `python3 -m pr_guard <mode> ...` works directly.

## Repository detection

The tool is repository-agnostic. The target repository resolves in this
order, and the tool refuses to run (exit 2) when nothing resolves:

1. `--repo OWNER/NAME` — global flag before the subcommand;
2. the `PR_GUARD_REPO=OWNER/NAME` environment variable;
3. `git remote get-url origin` of the current directory — the scp form
   `git@github.com:O/R.git`, `https://github.com/O/R.git`, and
   `ssh://git@github.com/O/R.git` all parse (trailing `/` and `.git`
   optional). Only `github.com` remotes resolve: every `gh` subprocess
   the tool runs is host-pinned to github.com, so a remote naming any
   other host would configure a target the tool can never reach.

## Modes

```
pr-guard [--repo OWNER/NAME] survey     <pr>
pr-guard [--repo OWNER/NAME] wait       <pr> [--timeout-secs <n>] [--accept-standing]
pr-guard [--repo OWNER/NAME] resolve    <pr>
pr-guard [--repo OWNER/NAME] pre-merge  <pr>
pr-guard [--repo OWNER/NAME] merge      <pr> <head-sha> <base> [--quiet-secs <n>]
pr-guard [--repo OWNER/NAME] harden     <pr>
```

- **survey <pr>** — print every review thread's classification
  (`resolved` / `receipted` / `DANGER`), a summary count line, and the
  BOT REACTION line. A report, not a gate: always exits 0.
- **wait <pr>** — poll ONLY the review bot's PR reaction until a
  terminal state or the timeout (default 600 s). Exit 0 = a watched
  THUMBS_UP; 3 = findings (EYES -> NONE confirmed); 1 = timeout;
  2 = usage. The reaction never authorizes a merge by itself.
  `--accept-standing` is the opt-in fast path for already-passed
  PRs: a standing, DONE-classified THUMBS_UP exits 0 immediately,
  bypassing the observation and review-evidence gates (the staleness
  classification still applies — a +1 predating the head push or
  round boundary keeps holding). The accepted risk: a standing pass
  may predate an unposted new round; thread state remains the merge
  authority.
- **resolve <pr>** — after receipts land, resolve ONLY receipted
  threads, re-verifying each immediately before and after its
  mutation; refuses while any DANGER thread remains.
- **pre-merge <pr>** — the gate: no DANGER thread, head/base unchanged
  across the survey, and an ACTIVE server-side ruleset requiring
  review-thread resolution. CLEAN names the exact guarded merge
  command.
- **merge <pr> <head-sha> <base>** — the guarded merge act: re-runs the
  entire gate and dispatches `gh pr merge --merge --match-head-commit`
  in the SAME process, polls the landing, re-surveys post-merge, and
  auto-reverts (revert PR) if any DANGER thread appears. MERGED CLEAN
  only after a bounded quiet-period watch passes.
- **harden <pr>** — ensure the repository ruleset that makes
  review-thread resolution a server-side merge requirement on the
  protected bases. Idempotent.

## The reaction protocol (wait mode)

The review bot reacts ON the PR itself:

- **THUMBS_UP** — review complete and passed;
- **EYES** — review actively in progress;
- **none** — not started or stale.

The bot removes its EYES at round end: `+1` when it passed, NOTHING when
it found feedback — so a verified EYES -> NONE transition that persists
through the next probe means FINDINGS (exit 3: fix, receipt, re-wait).
A cold NONE (no EYES variant ever observed) lasting >= 10 s prints the
`@codex review` trigger HINT exactly once — the bot may have failed to
start; the tool never posts comments itself. The reaction is the cheap
DONE/ACTIVE signal only: thread state (survey / pre-merge) stays the
merge authority. For already-passed PRs, `wait --accept-standing` is
the documented opt-in fast path: it accepts a standing THUMBS_UP that
passed the staleness classification without the observed-transition
and review-evidence gates — the risk accepted is that a standing pass
may predate an unposted new round.

## Tests

The package deliberately ships its own test modules — they are the
tool's hardening record (see below). Run the full suite from a checkout:

```sh
python3 -m unittest pr_guard.pr_guard_test        # aggregate: 603 tests
python3 -m unittest discover -s . -t . -p "pr_guard*_test.py"   # discovery: the same 603
```

Both loader routes must report the same count with zero failures — the
aggregate == discovery equality is the suite's exact-once guarantee.

## Design history

This tool was extracted from a 33-round hardened in-repo lineage (the
`.omo/start-work/pr_guard*.py` family, PRs #36 through #49 of its
origin repository, growing from one file to a 144-module family under a
250 pure-LOC-per-module ceiling). Every round was driven by a reviewer
or incident finding — the post-merge blind-merge incident that created
it, the GH_REPO/GH_HOST split-brain pins, the poll-timeout cancel and
merge-queue settlement, the revert identity gate that stopped
auto-reverting historical merges, and the reaction-signal wait with its
round-boundary/HEAD-stability refinements. The provenance comments
(thread IDs, PR/round numbers) throughout the source are that record;
see the design-history note in the source repository for the
reaction-signal protocol's user-taught refinements.
