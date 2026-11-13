"""Regression tests for the B2 fix (Phase 10 pre-push review, P032/P033):
`DATABASE_PATH` defaulting, env-var override, CWD-independent path
resolution, and `get_session_local()`'s fail-fast/no-silent-create
behavior.

`app.config` computes `DATABASE_PATH` once at import time, so testing
different env vars/CWDs requires a fresh import each time — done via
`importlib.reload`, with `DATABASE_PATH`/`DATASET_MODE` cleared from
the environment first so a developer's own shell doesn't leak into the
test.
"""

import importlib
from pathlib import Path

import pytest
from sqlalchemy import select

import app.config as config_module
import app.db.session as session_module
from app.data_generation.generator import generate_dataset, load_dataset
from app.db.models import JobRequisition


@pytest.fixture()
def clean_env(monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("DATASET_MODE", raising=False)
    yield


def _reload_config():
    return importlib.reload(config_module)


def test_default_database_path_points_at_starter_db_under_backend_root(clean_env):
    reloaded = _reload_config()
    assert reloaded.DATABASE_PATH == str(reloaded.BACKEND_ROOT / "data" / "talentflow_starter.db")
    assert Path(reloaded.DATABASE_PATH).is_absolute()


def test_database_path_env_override_wins(clean_env, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "data/talentflow_full.db")
    reloaded = _reload_config()
    assert reloaded.DATABASE_PATH == str(reloaded.BACKEND_ROOT / "data" / "talentflow_full.db")


def test_database_path_env_override_absolute_path_passed_through(clean_env, monkeypatch, tmp_path):
    absolute = tmp_path / "somewhere_else.db"
    monkeypatch.setenv("DATABASE_PATH", str(absolute))
    reloaded = _reload_config()
    assert reloaded.DATABASE_PATH == str(absolute)


def test_database_path_resolves_relative_to_backend_root_not_cwd(clean_env, monkeypatch, tmp_path):
    original_cwd = Path.cwd()
    monkeypatch.chdir(tmp_path)
    try:
        reloaded = _reload_config()
        # Same resolved path regardless of the process's current working
        # directory - the real bug this fixes: a bare relative path like
        # "data/talentflow_starter.db" previously only worked by accident,
        # when the caller's CWD happened to be backend/.
        assert reloaded.DATABASE_PATH == str(reloaded.BACKEND_ROOT / "data" / "talentflow_starter.db")
        assert str(tmp_path) not in reloaded.DATABASE_PATH
    finally:
        monkeypatch.chdir(original_cwd)
        _reload_config()  # restore the real module state for later tests


@pytest.fixture()
def reset_session_cache():
    """get_session_local() memoizes its result in a module-level global;
    reset it before and after each test in this group so tests don't
    leak a cached sessionmaker (or its absence) into each other."""
    session_module._default_session_local = None
    yield
    session_module._default_session_local = None


def test_get_session_local_raises_when_database_missing(monkeypatch, tmp_path, reset_session_cache):
    monkeypatch.setattr(session_module, "DATABASE_PATH", str(tmp_path / "does_not_exist.db"))
    with pytest.raises(session_module.DatabaseNotConfiguredError, match="does_not_exist.db"):
        session_module.get_session_local()
    # The whole point of this check: no file should have been created.
    assert not (tmp_path / "does_not_exist.db").exists()


def test_get_session_local_succeeds_against_a_freshly_generated_starter_db(monkeypatch, tmp_path, reset_session_cache):
    """Does not depend on backend/data/talentflow_starter.db already
    existing (a fresh clone wouldn't have it) - generates its own, same
    pattern test_phase6_detection_evaluation.py's fixtures already use."""
    dataset = generate_dataset("starter", seed=20261022)
    db_path = tmp_path / "fresh_starter.db"
    load_dataset(dataset, db_path)

    monkeypatch.setattr(session_module, "DATABASE_PATH", str(db_path))
    session_local = session_module.get_session_local()
    with session_local() as session:
        count = session.execute(select(JobRequisition)).scalars().all()
        assert len(count) == 10  # starter mode: 10 requisitions, real data, not an empty schema
