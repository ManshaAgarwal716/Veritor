from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import PositiveFloat, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.adapters.http import RegistryLimits
from app.analysis.models import AnalysisLimits
from app.archives.extract import ExtractionLimits
from app.comparison.models import ComparisonLimits


def _find_repo_root(source_file: Path | None = None) -> Path:
    """Resolve the repository or application root across local and containerized environments."""
    current = (source_file or Path(__file__)).resolve()
    # 1. In local dev, parents[2] is the workspace root containing .git, docker-compose.yml, or .env
    if len(current.parents) > 2:
        candidate = current.parents[2]
        if (
            (candidate / ".git").exists()
            or (candidate / "docker-compose.yml").exists()
            or (candidate / ".env").exists()
        ):
            return candidate

    # 2. In Docker containers (WORKDIR /app, app package at /app/app),
    # parents[1] is /app containing pyproject.toml, alembic.ini, or mounted .env
    if len(current.parents) > 1:
        candidate_app = current.parents[1]
        if (candidate_app / "alembic.ini").exists() or (candidate_app / "pyproject.toml").exists():
            return candidate_app

    # 3. Fallback to parents[2] if available, else current.parent
    return current.parents[2] if len(current.parents) > 2 else current.parent


REPO_ROOT = _find_repo_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            REPO_ROOT / ".env",
            Path.cwd() / ".env",
            ".env",
        ),
        env_prefix="VERITOR_",
        extra="ignore",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    database_url: str | None = None

    ollama_base_url: str = "http://127.0.0.1:11434"
    triage_model: str = "phi4-mini"
    explain_model: str = "qwen2.5-coder:7b"

    registry_connect_timeout_seconds: PositiveFloat = RegistryLimits.connect_timeout_seconds
    registry_read_timeout_seconds: PositiveFloat = RegistryLimits.read_timeout_seconds
    registry_metadata_deadline_seconds: PositiveFloat = RegistryLimits.metadata_deadline_seconds
    registry_download_deadline_seconds: PositiveFloat = RegistryLimits.download_deadline_seconds
    registry_max_metadata_bytes: PositiveInt = RegistryLimits.max_metadata_bytes
    registry_max_artifact_bytes: PositiveInt = RegistryLimits.max_artifact_bytes
    registry_max_source_archive_bytes: PositiveInt = RegistryLimits.max_source_archive_bytes

    github_token: SecretStr | None = None

    extraction_max_archive_bytes: PositiveInt = ExtractionLimits.max_archive_bytes
    extraction_max_total_bytes: PositiveInt = ExtractionLimits.max_total_bytes
    extraction_max_file_bytes: PositiveInt = ExtractionLimits.max_file_bytes
    extraction_max_entries: PositiveInt = ExtractionLimits.max_entries
    extraction_max_compression_ratio: PositiveInt = ExtractionLimits.max_compression_ratio
    extraction_deadline_seconds: PositiveFloat = ExtractionLimits.deadline_seconds

    comparison_max_diff_file_bytes: PositiveInt = ComparisonLimits.max_diff_file_bytes
    comparison_max_diff_lines: PositiveInt = ComparisonLimits.max_diff_lines
    comparison_max_diff_output_bytes: PositiveInt = ComparisonLimits.max_diff_output_bytes
    comparison_max_total_diff_bytes: PositiveInt = ComparisonLimits.max_total_diff_bytes

    analysis_max_file_bytes: PositiveInt = AnalysisLimits.max_file_bytes
    analysis_deadline_seconds: PositiveFloat = AnalysisLimits.deadline_seconds
    provenance_timeout_seconds: PositiveFloat = 60.0

    def registry_limits(self) -> RegistryLimits:
        return RegistryLimits(
            connect_timeout_seconds=self.registry_connect_timeout_seconds,
            read_timeout_seconds=self.registry_read_timeout_seconds,
            metadata_deadline_seconds=self.registry_metadata_deadline_seconds,
            download_deadline_seconds=self.registry_download_deadline_seconds,
            max_metadata_bytes=self.registry_max_metadata_bytes,
            max_artifact_bytes=self.registry_max_artifact_bytes,
            max_source_archive_bytes=self.registry_max_source_archive_bytes,
        )

    def extraction_limits(self) -> ExtractionLimits:
        return ExtractionLimits(
            max_archive_bytes=self.extraction_max_archive_bytes,
            max_total_bytes=self.extraction_max_total_bytes,
            max_file_bytes=self.extraction_max_file_bytes,
            max_entries=self.extraction_max_entries,
            max_compression_ratio=self.extraction_max_compression_ratio,
            deadline_seconds=self.extraction_deadline_seconds,
        )

    def comparison_limits(self) -> ComparisonLimits:
        return ComparisonLimits(
            max_diff_file_bytes=self.comparison_max_diff_file_bytes,
            max_diff_lines=self.comparison_max_diff_lines,
            max_diff_output_bytes=self.comparison_max_diff_output_bytes,
            max_total_diff_bytes=self.comparison_max_total_diff_bytes,
        )

    def analysis_limits(self) -> AnalysisLimits:
        return AnalysisLimits(
            max_file_bytes=self.analysis_max_file_bytes,
            deadline_seconds=self.analysis_deadline_seconds,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
