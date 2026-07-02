"""Screenshot comparison on synthetic images."""
import pytest
from PIL import Image

import config
import utils


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))


def _make(path, color, size=(50, 50)):
    Image.new("RGB", size, color).save(path)
    return str(path)


def test_identical_images_zero_diff(tmp_path):
    a = _make(tmp_path / "a.png", (200, 10, 10))
    b = _make(tmp_path / "b.png", (200, 10, 10))
    r = utils.compare_screenshots(a, b)
    assert r["success"] and r["diff_percentage"] == 0


def test_different_images_full_diff(tmp_path):
    a = _make(tmp_path / "a.png", (255, 255, 255))
    b = _make(tmp_path / "b.png", (0, 0, 0))
    r = utils.compare_screenshots(a, b)
    assert r["diff_percentage"] == 100


def test_size_mismatch_padded(tmp_path):
    a = _make(tmp_path / "a.png", (0, 0, 0), (50, 50))
    b = _make(tmp_path / "b.png", (0, 0, 0), (100, 50))
    r = utils.compare_screenshots(a, b)
    assert r["dimensions"] == {"width": 100, "height": 50}
    assert 0 < r["diff_percentage"] <= 50


def test_missing_file_reports_error(tmp_path):
    a = _make(tmp_path / "a.png", (0, 0, 0))
    r = utils.compare_screenshots(a, str(tmp_path / "missing.png"))
    assert r["success"] is False
