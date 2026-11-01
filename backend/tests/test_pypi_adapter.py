"""Unit tests for the PyPI adapter."""

import hashlib
from pathlib import Path

import httpx
import pytest

from app.adapters.base import DependencyKind
from app.adapters.errors import (
    InvalidPackageRequestError,
    PackageNotFoundError,
)
from app.adapters.pypi import PyPIAdapter, _discover_repository, _normalize_repository_url
from app.schemas.scans import Ecosystem


def test_normalize_repository_url():
    assert (
        _normalize_repository_url("https://github.com/psf/requests.git")
        == "https://github.com/psf/requests"
    )
    assert (
        _normalize_repository_url("git+https://github.com/pallets/flask")
        == "https://github.com/pallets/flask"
    )
    assert (
        _normalize_repository_url("git@github.com:encode/httpx.git")
        == "https://github.com/encode/httpx"
    )
    assert _normalize_repository_url("psf/requests") == "https://github.com/psf/requests"
    assert _normalize_repository_url("invalid-url") is None
    assert _normalize_repository_url("") is None


def test_discover_repository():
    info_with_project_urls = {
        "project_urls": {
            "Homepage": "https://requests.readthedocs.io",
            "Source": "https://github.com/psf/requests",
            "Documentation": "https://requests.readthedocs.io",
        }
    }
    repo = _discover_repository(info_with_project_urls)
    assert repo is not None
    assert repo.url == "https://github.com/psf/requests"

    info_with_home_page = {
        "home_page": "https://github.com/pallets/click",
    }
    repo = _discover_repository(info_with_home_page)
    assert repo is not None
    assert repo.url == "https://github.com/pallets/click"

    info_none = {"project_urls": {}, "home_page": None}
    assert _discover_repository(info_none) is None


@pytest.mark.anyio
async def test_fetch_metadata_success():
    package_data = {
        "info": {
            "name": "sample-pkg",
            "version": "1.0.0",
            "summary": "A sample Python package",
            "license": "MIT",
            "home_page": "https://sample.org",
            "project_urls": {
                "Source": "https://github.com/example/sample-pkg",
            },
            "requires_dist": [
                "urllib3<3,>=1.21.1",
                "certifi>=2017.4.17",
                "socks ; extra == 'socks'",
            ],
        },
        "urls": [
            {
                "packagetype": "sdist",
                "filename": "sample_pkg-1.0.0.tar.gz",
                "url": "https://files.pythonhosted.org/packages/source/s/sample-pkg/sample_pkg-1.0.0.tar.gz",
                "digests": {"sha256": "a" * 64},
                "upload_time_iso_8601": "2024-01-01T12:00:00Z",
            },
            {
                "packagetype": "bdist_wheel",
                "filename": "sample_pkg-1.0.0-py3-none-any.whl",
                "url": "https://files.pythonhosted.org/packages/wheel/sample_pkg-1.0.0-py3-none-any.whl",
                "digests": {"sha256": "b" * 64},
                "upload_time_iso_8601": "2024-01-01T12:01:00Z",
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/pypi/sample-pkg/1.0.0/json":
            return httpx.Response(200, json=package_data)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PyPIAdapter(client)
        meta = await adapter.fetch_metadata("sample-pkg", "1.0.0")

        assert meta.ecosystem is Ecosystem.PYPI
        assert meta.name == "sample-pkg"
        assert meta.version == "1.0.0"
        assert meta.description == "A sample Python package"
        assert meta.license == "MIT"
        assert meta.repository is not None
        assert meta.repository.url == "https://github.com/example/sample-pkg"

        # Dependencies
        assert len(meta.dependencies) == 3
        assert meta.dependencies[0].name == "urllib3"
        assert meta.dependencies[0].kind is DependencyKind.RUNTIME
        assert meta.dependencies[2].kind is DependencyKind.OPTIONAL

        # Artifacts
        assert len(meta.artifacts) == 2
        assert meta.artifacts[0].filename == "sample_pkg-1.0.0.tar.gz"
        assert meta.artifacts[0].hashes[0].hex_digest == "a" * 64


@pytest.mark.anyio
async def test_fetch_metadata_validation_errors():
    transport = httpx.MockTransport(lambda req: httpx.Response(200))
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PyPIAdapter(client)

        with pytest.raises(InvalidPackageRequestError):
            await adapter.fetch_metadata("invalid name with spaces", "1.0.0")

        with pytest.raises(InvalidPackageRequestError):
            await adapter.fetch_metadata("valid-pkg", "invalid_ver")


@pytest.mark.anyio
async def test_fetch_metadata_404_handling():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PyPIAdapter(client)

        with pytest.raises(PackageNotFoundError):
            await adapter.fetch_metadata("nonexistent-pkg", "1.0.0")


@pytest.mark.anyio
async def test_download_artifact(tmp_path: Path):
    content = b"sample wheel contents"
    digest = hashlib.sha256(content).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "files.pythonhosted.org":
            return httpx.Response(200, stream=httpx.ByteStream(content))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = PyPIAdapter(client)

        from app.adapters.base import ArtifactHash, ArtifactInfo

        artifact = ArtifactInfo(
            url="https://files.pythonhosted.org/packages/wheel/sample-1.0.0.whl",
            filename="sample-1.0.0.whl",
            hashes=(ArtifactHash(algorithm="sha256", hex_digest=digest),),
        )

        dest = tmp_path / "downloads"
        downloaded = await adapter.download_artifact(artifact, dest)

        assert downloaded.path.exists()
        assert downloaded.sha256 == digest
        assert downloaded.size_bytes == len(content)
