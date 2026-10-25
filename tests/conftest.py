from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from clearcommit_teams.context import build_context
from clearcommit_teams.paths import PROJECT_ROOT

TEST_DATA_ROOT = PROJECT_ROOT / "data" / "_test"


@pytest.fixture
def data_dir() -> Path:
    TEST_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_DATA_ROOT / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def ctx(data_dir: Path):
    return build_context(data_dir)


@pytest.fixture
def helio(ctx):
    return ctx.repo.get_session("s_sample_helio")
