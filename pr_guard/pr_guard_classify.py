"""Pure classification core for pr_guard.

Split from pr_guard_threads.py at the 250 pure-LOC ceiling (PR #37,
thread 3828232337): the Thread record, the bot allowlist, and the
DANGER/receipted/resolved classification. No I/O — unit-tested in
pr_guard_test.py; pr_guard_threads re-exports these names so existing
module re-exports these names so existing imports keep working.
"""

from .pr_guard_common import RECEIPT_AUTHORS

BOT_AUTHORS = frozenset(
    {"chatgpt-codex-connector", "github-actions[bot]", "renovate[bot]"}
)
CLASSES = ("resolved", "receipted", "DANGER")


class Thread:
    def __init__(
        self,
        node_id: str,
        head_id: int | None,
        last_id: int | None,
        last_author: str | None,
        last_author_type: str | None,
        last_body: str,
        is_resolved: bool,
        is_outdated: bool,
    ) -> None:
        self.node_id = node_id
        self.head_id = head_id
        self.last_id = last_id
        self.last_author = last_author
        self.last_author_type = last_author_type
        self.last_body = last_body
        self.is_resolved = is_resolved
        self.is_outdated = is_outdated
        self.classification = ""

    @property
    def label(self) -> str:
        return str(self.head_id) if self.head_id is not None else self.node_id

    @property
    def last_label(self) -> str:
        return str(self.last_id) if self.last_id is not None else "?"


def last_comment_is_human(thread: Thread) -> bool:
    """User-typed author outside the bot allowlist (fail closed)."""
    return (
        thread.last_author_type == "User"
        and thread.last_author is not None
        and thread.last_author not in BOT_AUTHORS
    )


def last_comment_is_trusted(thread: Thread) -> bool:
    """Human AND authored by a trusted receipt account (thread
    3828399604 — an outside User's "this is still broken" reply is not
    a receipt; untrusted human last words classify DANGER)."""
    return last_comment_is_human(thread) and (
        thread.last_author in RECEIPT_AUTHORS
    )


def classify(thread: Thread) -> str:
    if thread.is_resolved:
        # Thread 3828232337: resolve state alone is not a receipt — a
        # thread resolved while a bot (or an UNTRUSTED human, thread
        # 3828399604) holds the LAST word stays DANGER so a later
        # pre-merge cannot read the drifted thread as safe; head ==
        # last is fine — the trusted self-resolver IS the receipt.
        if last_comment_is_trusted(thread):
            return "resolved"
        return "DANGER"
    # Thread 3827843271: a human-authored FINDING nobody has replied to
    # has head == last (the same comment) — the finding itself is not a
    # receipt, so an actual later reply (last_id != head_id) authored by
    # a human is required before the thread counts as receipted.
    # Thread 3827503034: fail closed for ANY bot — the allowlist alone
    # misread bots outside it (Dependabot, Copilot, renamed review
    # apps) as human receipts. __typename 'User' is the only human
    # actor shape; Bot/Organization/Mannequin and unknown types (and
    # deleted authors) are DANGER, as are User-typed allowlisted bots.
    # Thread 3827397510: isOutdated is deliberately NOT consulted — a
    # moved hunk may still carry the defect, so only a receipt (or an
    # explicit human resolve) clears a finding. Thread 3828399604: the
    # receipt must additionally come from a TRUSTED account — any
    # outside User's follow-up is a new human word on the finding, not
    # proof it was handled.
    if last_comment_is_trusted(thread) and thread.last_id != thread.head_id:
        return "receipted"
    return "DANGER"
