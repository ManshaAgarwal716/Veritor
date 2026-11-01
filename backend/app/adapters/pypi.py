"""Adapter for the Python Package Index (https://pypi.org)."""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import quote, urlsplit

import httpx

from app.adapters.base import (
    ArtifactHash,
    ArtifactInfo,
    Dependency,
    DependencyKind,
    DownloadedArtifact,
    PackageAdapter,
    PackageMetadata,
    SourceRepository,
)
from app.adapters.errors import (
    InvalidPackageRequestError,
    InvalidRegistryResponseError,
    PackageNotFoundError,
    RegistryNotFoundError,
    VersionNotFoundError,
)
from app.adapters.http import RegistryLimits, download_verified, fetch_json
from app.schemas.scans import PYPI_NAME, Ecosystem, _is_pep440

PYPI_HOST = "pypi.org"
PYPI_URL = f"https://{PYPI_HOST}"
PYTHONHOSTED_HOST = "files.pythonhosted.org"

_REPOSITORY_URL_KEYS = (
    "source",
    "source code",
    "source-code",
    "repository",
    "code",
    "github",
    "homepage",
    "home",
    "upstream",
)

_REPOSITORY_SCHEMES = {"git", "git+https", "git+http", "git+ssh", "https", "http", "ssh"}
_HOST_SHORTHANDS = {
    "github": "github.com",
    "gitlab": "gitlab.com",
    "bitbucket": "bitbucket.org",
}
_GITHUB_SHORTHAND = re.compile(r"[\w.-]+/[\w.-]+")
_SCP_REPOSITORY = re.compile(r"(?:[\w.-]+@)([\w.-]+):(?!/)(.+)")


def _normalize_repository_url(declared: str) -> str | None:
    """Normalize a declared repository URL to https, or return None if not recognized."""
    value = declared.strip()
    if not value or any(ord(c) < 0x21 for c in value):
        return None

    host_prefix, separator, rest = value.partition(":")
    if separator and host_prefix in _HOST_SHORTHANDS and not rest.startswith("/"):
        value = f"https://{_HOST_SHORTHANDS[host_prefix]}/{rest}"
    elif _GITHUB_SHORTHAND.fullmatch(value):
        value = f"https://github.com/{value}"
    elif scp := _SCP_REPOSITORY.fullmatch(value):
        value = f"https://{scp.group(1)}/{scp.group(2)}"

    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        return None

    if parts.scheme not in _REPOSITORY_SCHEMES or not host or "." not in host:
        return None

    path = parts.path.rstrip("/").removesuffix(".git")
    if not path or ".." in path.split("/"):
        return None
    return f"https://{host}{path}"


def _discover_repository(info: dict[str, Any]) -> SourceRepository | None:
    """Discover source repository from PyPI info project_urls and home_page."""
    project_urls = info.get("project_urls")
    candidates: list[str] = []

    if isinstance(project_urls, dict):
        # Check high priority keys first
        for key in _REPOSITORY_URL_KEYS:
            for k, val in project_urls.items():
                if isinstance(k, str) and isinstance(val, str) and k.strip().lower() == key:
                    candidates.append(val)

        # Fallback to any project_url containing github.com or gitlab.com
        for val in project_urls.values():
            if isinstance(val, str) and ("github.com" in val or "gitlab.com" in val):
                candidates.append(val)

    home_page = info.get("home_page")
    if isinstance(home_page, str) and home_page.strip():
        candidates.append(home_page.strip())

    for cand in candidates:
        norm = _normalize_repository_url(cand)
        if norm:
            return SourceRepository(declared=cand, url=norm)

    return None


def _parse_dependencies(requires_dist: list[Any] | None) -> tuple[Dependency, ...]:
    """Parse PyPI requires_dist strings into Dependency models."""
    if not isinstance(requires_dist, list):
        return ()

    deps: list[Dependency] = []
    for raw in requires_dist:
        if not isinstance(raw, str) or not raw.strip():
            continue
        # Format e.g. "urllib3 (<3,>=1.21.1) ; extra == 'socks'" or "requests >= 2.0"
        clean = raw.strip()
        is_optional = "extra ==" in clean
        kind = DependencyKind.OPTIONAL if is_optional else DependencyKind.RUNTIME

        dep_name_part = clean.split(";")[0].strip()
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*(.*)$", dep_name_part)
        if match:
            name = match.group(1).strip()
            spec = match.group(2).strip("() ").strip()
            specifier = spec if spec else None
        else:
            name = dep_name_part
            specifier = None

        deps.append(Dependency(name=name, specifier=specifier, kind=kind))

    return tuple(deps)


def _require_pypi_download_url(url: str) -> None:
    """Enforce that artifact downloads originate from files.pythonhosted.org."""
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise InvalidRegistryResponseError(f"Malformed PyPI artifact URL: {url!r}") from exc

    if (
        parts.scheme != "https"
        or parts.netloc != PYTHONHOSTED_HOST
        or parts.query
        or parts.fragment
        or not (
            parts.path.endswith(".tar.gz")
            or parts.path.endswith(".zip")
            or parts.path.endswith(".whl")
        )
    ):
        raise InvalidRegistryResponseError(
            f"PyPI artifact is not hosted by {PYTHONHOSTED_HOST}: {url!r}"
        )


class PyPIAdapter(PackageAdapter):
    """Adapter for the official Python Package Index (pypi.org)."""

    ecosystem: ClassVar[Ecosystem] = Ecosystem.PYPI

    def __init__(self, client: httpx.AsyncClient, limits: RegistryLimits | None = None) -> None:
        self._client = client
        self._limits = limits or RegistryLimits()

    async def fetch_metadata(self, name: str, version: str) -> PackageMetadata:
        """Fetch exact version metadata from the PyPI JSON API."""
        if not isinstance(name, str) or not PYPI_NAME.fullmatch(name):
            raise InvalidPackageRequestError(f"Not a valid PyPI package name: {name!r}")
        if not isinstance(version, str) or not _is_pep440(version):
            raise InvalidPackageRequestError(f"Not a valid PEP 440 version: {version!r}")

        # PyPI provides https://pypi.org/pypi/<package>/<version>/json
        url = f"{PYPI_URL}/pypi/{quote(name)}/{quote(version)}/json"
        try:
            document = await fetch_json(self._client, url, self._limits)
        except RegistryNotFoundError as exc:
            # Fallback check if package exists at all
            pkg_url = f"{PYPI_URL}/pypi/{quote(name)}/json"
            try:
                pkg_doc = await fetch_json(self._client, pkg_url, self._limits)
                releases = pkg_doc.get("releases", {})
                if version not in releases:
                    raise VersionNotFoundError(
                        f"Version {version} of PyPI package {name} does not exist"
                    ) from exc
                document = self._extract_version_doc(pkg_doc, name, version)
            except RegistryNotFoundError:
                raise PackageNotFoundError(f"PyPI package {name} does not exist") from exc

        return self._parse_version(document, name, version)

    def _extract_version_doc(
        self, pkg_doc: dict[str, Any], name: str, version: str
    ) -> dict[str, Any]:
        info = pkg_doc.get("info", {}).copy()
        info["version"] = version
        urls = pkg_doc.get("releases", {}).get(version, [])
        return {"info": info, "urls": urls}

    def _parse_version(self, document: dict[str, Any], name: str, version: str) -> PackageMetadata:
        info = document.get("info")
        if not isinstance(info, dict):
            raise InvalidRegistryResponseError("PyPI document missing 'info' section")

        package_name = str(info.get("name") or name)
        summary = info.get("summary") or info.get("description")
        description = str(summary) if summary else None
        license_str = info.get("license")
        license_val = str(license_str) if license_str else None
        homepage = info.get("home_page")
        homepage_val = str(homepage) if homepage else None

        repository = _discover_repository(info)
        dependencies = _parse_dependencies(info.get("requires_dist"))

        # Release artifacts
        urls = document.get("urls")
        if not isinstance(urls, list):
            urls = []

        artifacts: list[ArtifactInfo] = []
        published_at: datetime | None = None

        # Prioritize sdist (.tar.gz / .zip) first for source comparisons, then wheels (.whl)
        sdist_items: list[dict[str, Any]] = []
        wheel_items: list[dict[str, Any]] = []

        for item in urls:
            if not isinstance(item, dict):
                continue
            packagetype = item.get("packagetype", "")
            filename = item.get("filename", "")
            if packagetype == "sdist" or filename.endswith(".tar.gz") or filename.endswith(".zip"):
                sdist_items.append(item)
            elif packagetype == "bdist_wheel" or filename.endswith(".whl"):
                wheel_items.append(item)

        ordered_items = sdist_items + wheel_items

        for item in ordered_items:
            download_url = item.get("url")
            filename = item.get("filename")
            digests = item.get("digests", {})
            upload_time = item.get("upload_time_iso_8601") or item.get("upload_time")

            if not download_url or not filename:
                continue

            try:
                _require_pypi_download_url(download_url)
            except InvalidRegistryResponseError:
                continue

            hashes: list[ArtifactHash] = []
            if isinstance(digests, dict) and "sha256" in digests:
                sha256_hex = str(digests["sha256"]).lower()
                if re.fullmatch(r"^[0-9a-f]{64}$", sha256_hex):
                    hashes.append(ArtifactHash(algorithm="sha256", hex_digest=sha256_hex))

            if hashes:
                artifacts.append(
                    ArtifactInfo(
                        url=download_url,
                        filename=filename,
                        hashes=tuple(hashes),
                    )
                )

            if published_at is None and upload_time:
                try:
                    published_at = datetime.fromisoformat(str(upload_time).replace("Z", "+00:00"))
                except ValueError:
                    pass

        # Check for install / build hooks declared in entry points or setup
        entry_points = info.get("entry_points") or {}
        if not isinstance(entry_points, dict):
            entry_points = {}

        return PackageMetadata(
            ecosystem=Ecosystem.PYPI,
            name=package_name,
            version=version,
            description=description,
            license=license_val,
            homepage=homepage_val,
            repository=repository,
            source_commit=None,
            published_at=published_at,
            dependencies=dependencies,
            scripts={},
            has_install_script=False,
            entry_points=entry_points,
            artifacts=tuple(artifacts),
            manifest=document,
        )

    async def download_artifact(
        self, artifact: ArtifactInfo, destination_dir: Path
    ) -> DownloadedArtifact:
        """Download a PyPI artifact and verify its sha256 checksum."""
        _require_pypi_download_url(artifact.url)
        return await download_verified(self._client, artifact, destination_dir, self._limits)
