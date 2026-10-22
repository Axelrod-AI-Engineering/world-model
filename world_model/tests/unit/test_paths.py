"""The roots (axelrod_wm/paths.py): one test per constant, and the override the Docker image uses."""

import importlib

from axelrod_wm import paths


def test_repo_root_is_the_workspace_root():
    assert paths.REPO_ROOT.is_absolute()
    assert (paths.REPO_ROOT / "pyproject.toml").exists() and (paths.REPO_ROOT / "world_model" / "pyproject.toml").exists()
    assert (paths.REPO_ROOT / "configs" / "world_model.toml").exists()          # the stage settings live at the root


def test_wm_root_holds_the_members_files():
    assert paths.WM_ROOT == paths.REPO_ROOT / "world_model"
    for name in ("examples", "taxonomy", "configs", "web", "src"):
        assert (paths.WM_ROOT / name).is_dir(), name
    assert (paths.WM_ROOT / "configs" / "default.yaml").exists()


def test_axelrod_root_moves_both_roots(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    try:
        moved = importlib.reload(paths)
        assert moved.REPO_ROOT == tmp_path and moved.WM_ROOT == tmp_path / "world_model"
    finally:
        monkeypatch.delenv(paths.ROOT_ENV)
        importlib.reload(paths)
    assert paths.REPO_ROOT != tmp_path
