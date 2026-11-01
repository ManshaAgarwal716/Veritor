"""Detect newly published package versions from registries."""

import logging
from urllib.parse import quote

import httpx
from packaging.version import InvalidVersion, Version

from app.schemas.scans import Ecosystem

logger = logging.getLogger(__name__)

NPM_REGISTRY_URL = "https://registry.npmjs.org"
PYPI_REGISTRY_URL = "https://pypi.org"


async def fetch_latest_version(
    client: httpx.AsyncClient,
    ecosystem: Ecosystem | str,
    package_name: str,
) -> str | None:
    """Fetch the latest released version for a package from its registry."""
    eco = Ecosystem(ecosystem) if isinstance(ecosystem, str) else ecosystem

    try:
        if eco is Ecosystem.NPM:
            url = f"{NPM_REGISTRY_URL}/{quote(package_name, safe='@')}"
            res = await client.get(url, timeout=10.0, headers={"Accept": "application/json"})
            if res.status_code != 200:
                logger.warning(
                    "Failed to fetch npm package %s: status %d", package_name, res.status_code
                )
                return None
            data = res.json()
            dist_tags = data.get("dist-tags", {})
            if isinstance(dist_tags, dict) and "latest" in dist_tags:
                return str(dist_tags["latest"])

            # Fallback: latest key in time
            times = data.get("time", {})
            if isinstance(times, dict):
                candidates = [v for v in times if v not in ("created", "modified")]
                if candidates:
                    return str(candidates[-1])

        elif eco is Ecosystem.PYPI:
            url = f"{PYPI_REGISTRY_URL}/pypi/{quote(package_name)}/json"
            res = await client.get(url, timeout=10.0, headers={"Accept": "application/json"})
            if res.status_code != 200:
                logger.warning(
                    "Failed to fetch PyPI package %s: status %d", package_name, res.status_code
                )
                return None
            data = res.json()
            info = data.get("info", {})
            if isinstance(info, dict) and "version" in info:
                return str(info["version"])

    except Exception as exc:
        logger.warning("Error fetching latest version for %s:%s: %s", eco, package_name, exc)
        return None

    return None


def is_newer_version(candidate: str, baseline: str | None) -> bool:
    """Check if candidate version is strictly newer than baseline version."""
    if not baseline:
        return True
    if candidate == baseline:
        return False

    try:
        cand_v = Version(candidate)
        base_v = Version(baseline)
        return cand_v > base_v
    except InvalidVersion:
        # Fallback to string inequality if non-standard versioning
        return candidate != baseline


async def check_package_update(
    client: httpx.AsyncClient,
    ecosystem: Ecosystem | str,
    package_name: str,
    current_version: str | None,
) -> tuple[bool, str | None]:
    """Check if a package has a newer version published than current_version."""
    latest = await fetch_latest_version(client, ecosystem, package_name)
    if not latest:
        return False, None

    has_update = is_newer_version(latest, current_version)
    return has_update, latest
