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


def test_split_tiles_crops_full_image(tmp_path):
    src = _make(tmp_path / "tall.png", (10, 20, 30), size=(400, 3500))
    tiles = utils.split_tiles(src, 1600)
    assert [t.endswith(f"_tile0{i}.png") for i, t in enumerate(tiles, 1)] == [True, True, True]
    heights = [Image.open(t).height for t in tiles]
    assert heights == [1600, 1600, 300]
    assert all(Image.open(t).width == 400 for t in tiles)


def test_split_tiles_short_image_is_one_tile(tmp_path):
    src = _make(tmp_path / "short.png", (1, 2, 3), size=(100, 800))
    tiles = utils.split_tiles(src, 1600)
    assert len(tiles) == 1 and Image.open(tiles[0]).height == 800
