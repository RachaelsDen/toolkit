"""PR issue-comment finding retrieval and classification for pr_guard.

user-observed 2026-09-19: first codex finding posted as an issue comment,
invisible to reviewThreads.

An all-findings receipt must contain the explicit ``receipt:all findings``
or ``receipt-all-findings`` token (case-insensitive; the space after ``:``
is optional).
"""

import re
from dataclasses import dataclass
from typing import TypeGuard

from .pr_guard_classify import REVIEW_BOT_AUTHORS
from .pr_guard_common import RECEIPT_AUTHORS
from .pr_guard_threads import excerpt

__all__ = [
    "FindingComment",
    "IssueComment",
    "classify_finding_comments",
    "login_is_bot",
    "report",
]

FINDING_BADGE = re.compile(
    r"\bP[012]\s+Badge\b|^\s*\*\*<sub>.*?\bP[012]\s+Badge\b", re.DOTALL
)
ALL_FINDINGS_RECEIPT = re.compile(
    r"\breceipt(?::\s*all\s+findings|-all-findings)\b", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class IssueComment:
    id: int
    author: str | None
    created_at: str
    body: str
    author_type: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class FindingComment:
    id: int
    author: str
    created_at: str
    body: str
    classification: str

    @property
    def label(self) -> str:
        return f"comment={self.id}"


def login_is_bot(login: str | None) -> TypeGuard[str]:
    return login is not None and (
        login in REVIEW_BOT_AUTHORS
        or login.removesuffix("[bot]") in REVIEW_BOT_AUTHORS
    )


def comment_is_bot(comment: IssueComment) -> bool:
    return login_is_bot(comment.author)


def comment_is_trusted_receipt(comment: IssueComment) -> bool:
    return comment.author in RECEIPT_AUTHORS and not comment_is_bot(comment)


def comment_effective_time(comment: IssueComment) -> str:
    return (comment.updated_at or comment.created_at) if comment_is_bot(comment) else comment.created_at


def comment_key(comment: IssueComment) -> tuple[str, int]:
    return comment_effective_time(comment), comment.id


def comment_is_clean_summary(comment: IssueComment) -> bool:
    return (
        comment_is_bot(comment)
        and FINDING_BADGE.search(comment.body) is None
        and (
            "Didn't find any major issues" in comment.body
            or "### 💡 Codex Review" in comment.body
        )
    )


def classify_finding_comments(comments: list[IssueComment]) -> list[FindingComment]:
    ordered = sorted(comments, key=comment_key)
    findings: list[FindingComment] = []
    for comment in ordered:
        if not login_is_bot(comment.author) or FINDING_BADGE.search(comment.body) is None:
            continue
        finding_time = comment_effective_time(comment)
        finding_is_edited = finding_time != comment.created_at
        replies = [
            reply
            for reply in ordered
            if (
                comment_effective_time(reply) > finding_time
                or (
                    comment_effective_time(reply) == finding_time
                    and (
                        (
                            comment_is_bot(reply)
                            and comment_effective_time(reply) != reply.created_at
                        )
                        or (
                            comment_effective_time(reply) == reply.created_at
                            and not finding_is_edited
                            and reply.id > comment.id
                        )
                    )
                )
            )
            and not comment_is_clean_summary(reply)
            and (not comment_is_bot(reply) or FINDING_BADGE.search(reply.body) is None)
            and (
                comment_is_bot(reply)
                or (
                    comment_is_trusted_receipt(reply)
                    and (
                        ALL_FINDINGS_RECEIPT.search(reply.body) is not None
                        or re.search(
                            rf"\bcomment\s*(?:=\s*|\s+){comment.id}\b|#{comment.id}\b",
                            reply.body,
                            re.IGNORECASE,
                        )
                        is not None
                    )
                )
            )
        ]
        last_reply = replies[-1] if replies else None
        last_reply_time = comment_effective_time(last_reply) if last_reply else None
        equal_time_edited_bot_reply = any(
            comment_is_bot(reply)
            and reply.updated_at is not None
            and reply.updated_at != reply.created_at
            and comment_effective_time(reply) == last_reply_time
            for reply in replies
        )
        classification = (
            "receipted"
            if last_reply is not None
            and comment_is_trusted_receipt(last_reply)
            and not equal_time_edited_bot_reply
            else "DANGER"
        )
        findings.append(
            FindingComment(
                comment.id,
                comment.author,
                comment.created_at,
                comment.body,
                classification,
            )
        )
    return findings


def report(comments: list[FindingComment]) -> None:
    for comment in comments:
        print(
            f'{comment.classification}-COMMENT comment={comment.id} '
            f'author={comment.author} "{excerpt(comment.body)}"'
        )
