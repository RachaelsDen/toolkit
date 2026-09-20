"""PR issue-comment finding retrieval and classification for pr_guard.

user-observed 2026-09-19: first codex finding posted as an issue comment,
invisible to reviewThreads.
"""

import re
from dataclasses import dataclass
from typing import TypeGuard

from .pr_guard_classify import BOT_AUTHORS
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
    r"\bP[012]\s+Badge\b|^\s*\*\*<sub>.*?\bBadge\b", re.DOTALL
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
        login in BOT_AUTHORS or login.removesuffix("[bot]") in BOT_AUTHORS
    )


def comment_is_bot(comment: IssueComment) -> bool:
    return comment.author_type == "Bot" or login_is_bot(comment.author)


def comment_is_trusted_receipt(comment: IssueComment) -> bool:
    return comment.author in RECEIPT_AUTHORS and not comment_is_bot(comment)


def comment_key(comment: IssueComment) -> tuple[str, int]:
    return comment.created_at, comment.id


def finding_key(comment: IssueComment) -> tuple[str, int]:
    return comment.updated_at or comment.created_at, comment.id


def classify_finding_comments(comments: list[IssueComment]) -> list[FindingComment]:
    ordered = sorted(comments, key=comment_key)
    findings: list[FindingComment] = []
    for comment in ordered:
        if (
            comment.author is None
            or not comment_is_bot(comment)
            or FINDING_BADGE.search(comment.body) is None
        ):
            continue
        replies = [
            reply
            for reply in ordered
            if comment_key(reply) > finding_key(comment)
            and (comment_is_bot(reply) or comment_is_trusted_receipt(reply))
        ]
        classification = (
            "receipted"
            if replies and comment_is_trusted_receipt(replies[-1])
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
