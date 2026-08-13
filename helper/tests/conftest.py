import pytest
from dashtouch_helper import webui


@pytest.fixture(autouse=True)
def isolate_dashtouch_home(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "URL_PATH", tmp_path / "webui-url")
    monkeypatch.setattr(webui, "LABELS_PATH", tmp_path / "labels.json")
