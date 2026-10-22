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


def test_yaml_files_skip_hidden_files(tmp_path):
    # a copy made on a Mac carries ._name.yaml resource forks and .DS_Store; they are not YAML
    (tmp_path / "b.yaml").write_text("x: 1\n")
    (tmp_path / "a.yaml").write_text("x: 2\n")
    (tmp_path / "._a.yaml").write_bytes(b"\x00\x05\x16\x07\xa3")
    (tmp_path / ".DS_Store").write_bytes(b"\xa3")
    (tmp_path / "notes.md").write_text("not yaml\n")
    assert [p.name for p in paths.yaml_files(tmp_path)] == ["a.yaml", "b.yaml"]


def test_a_construction_folder_with_resource_forks_still_loads(tmp_path):
    from axelrod_wm.engine.initialize import read_construction
    (tmp_path / "entities.yaml").write_text("{}\n")
    (tmp_path / "interactions.yaml").write_text("{}\n")
    (tmp_path / "construction").mkdir()
    (tmp_path / "construction" / "._acme.yaml").write_bytes(b"\x00\x05\x16\x07\xa3\xff")
    data, origin = read_construction(tmp_path)
    assert origin == {}
