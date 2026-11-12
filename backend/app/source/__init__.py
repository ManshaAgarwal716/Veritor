"""Source repository matching and archive retrieval package."""

from app.source.base import SourceHostAdapter, SourceNotMatchedError
from app.source.bitbucket import BitbucketSourceResolver, parse_bitbucket_repository
from app.source.github import GitHubSourceResolver, parse_github_repository
from app.source.gitlab import GitLabSourceResolver, parse_gitlab_repository
from app.source.models import (
    AnyRepository,
    BaseRepository,
    BitbucketRepository,
    Confidence,
    GitHubRepository,
    GitLabRepository,
    MatchMethod,
    MatchStatus,
    SourceArchive,
    SourceHost,
    SourceMatch,
    UncertainReason,
)
from app.source.resolvers import MultiHostSourceResolver

__all__ = [
    "AnyRepository",
    "BaseRepository",
    "BitbucketRepository",
    "BitbucketSourceResolver",
    "Confidence",
    "GitHubRepository",
    "GitHubSourceResolver",
    "GitLabRepository",
    "GitLabSourceResolver",
    "MatchMethod",
    "MatchStatus",
    "MultiHostSourceResolver",
    "SourceArchive",
    "SourceHost",
    "SourceHostAdapter",
    "SourceMatch",
    "SourceNotMatchedError",
    "UncertainReason",
    "parse_bitbucket_repository",
    "parse_github_repository",
    "parse_gitlab_repository",
]
