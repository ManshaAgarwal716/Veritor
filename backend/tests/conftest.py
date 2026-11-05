import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

# Prevent unresolvable docker-compose hostnames (e.g. postgres) from polluting local test runs
if "@postgres:" in (os.environ.get("VERITOR_DATABASE_URL") or "") or (
    "@postgres:" in (get_settings().database_url or "")
):
    os.environ["VERITOR_DATABASE_URL"] = ""
    get_settings.cache_clear()

TEST_ORIGIN = "http://frontend.test"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(log_level="INFO", cors_origins=[TEST_ORIGIN]))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
