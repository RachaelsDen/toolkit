"""PR issue-comment finding retrieval and classification for pr_guard.

user-observed 2026-09-19: first codex finding posted as an issue comment,
invisible to reviewThreads.
"""

import json
import re
import subprocess
from dataclasses import dataclass

from .pr_guard_classify import BOT_AUTHORS
from .pr_guard_common import RECEIPT_AUTHORS, REPO_NAME, REPO_OWNER, die, gh_env
from .pr_guard_threads import excerpt

__all__ = [
    "FindingComment",
    "IssueComment",
    "classify_finding_comments",
    "fetch_finding_comments",
    "report",
]

FINDING_BADGE = re.compile(
    r"\bP[012]\s+Badge\b|^\s*\*\*<sub>.*?\bBadge\b", re.DOTALL
)


@dataclass(frozen=True, slots=True)
class IssueComment:
    id: int
    author: str
    created_at: str
    body: str


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


def classify_finding_comments(comments: list[IssueComment]) -> list[FindingComment]:
    ordered = sorted(comments, key=lambda item: (item.created_at, item.id))
    findings: list[FindingComment] = []
    for comment in ordered:
        if comment.author not in BOT_AUTHORS or FINDING_BADGE.search(comment.body) is None:
            continue
        classification = "DANGER"
        if any(
            receipt.author in RECEIPT_AUTHORS
            and (receipt.created_at, receipt.id) > (comment.created_at, comment.id)
            for receipt in ordered
        ):
            classification = "receipted"
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


def fetch_finding_comments(pr: int) -> list[FindingComment]:
    proc = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr}/comments",
            "--paginate",
            "--slurp",
        ],
        capture_output=True,
        text=True,
        env=gh_env(),
    )
    if proc.returncode != 0:
        die(f"gh api exited {proc.returncode}: {proc.stderr.strip()}")
    pages = json.loads(proc.stdout)
    comments = [
        IssueComment(
            id=int(item["id"]),
            author=str(item["user"]["login"]),
            created_at=str(item["created_at"]),
            body=str(item["body"]),
        )
        for page in pages
        for item in page
    ]
    return classify_finding_comments(comments)


def report(comments: list[FindingComment]) -> None:
    for comment in comments:
        print(
            f'{comment.classification}-COMMENT comment={comment.id} '
            f'author={comment.author} "{excerpt(comment.body)}"'
        )
