from axelrod_wm.api import routes


def test_build_is_the_railway_commit(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    assert routes._build() is None
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "0123456789abcdef0123")
    assert routes._build() == "0123456789ab"
