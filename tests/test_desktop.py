"""Automated tests for Aqua Desktop components (Config, AppIndexer, Parabolic Dock, Spotlight)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aqua-desktop"))

from core.app_indexer import AppIndexer
from core.config import AquaConfig
from dock.dock import AquaDockModel, compute_parabolic_magnification
from spotlight.spotlight import SpotlightEngine, evaluate_math_expression


def test_config_persistence(tmp_path: Path) -> None:
    cfg_file = tmp_path / "settings.json"
    cfg = AquaConfig(config_path=cfg_file)
    assert cfg.get("appearance", "theme") == "dark"

    cfg.set("appearance", "theme", "light")
    cfg2 = AquaConfig(config_path=cfg_file)
    assert cfg2.get("appearance", "theme") == "light"


def test_dock_parabolic_magnification() -> None:
    base = 52
    # Cursor directly over icon center -> maximum scale (1.65 * 52 = 85.8)
    direct = compute_parabolic_magnification(cursor_x=100.0, icon_center_x=100.0, base_size=base, max_scale=1.65, radius=150.0)
    assert direct == round(52 * 1.65, 2)

    # Cursor far outside radius -> base size (52.0)
    far = compute_parabolic_magnification(cursor_x=400.0, icon_center_x=100.0, base_size=base, max_scale=1.65, radius=150.0)
    assert far == 52.0

    # Cursor halfway -> intermediate smooth magnification
    mid = compute_parabolic_magnification(cursor_x=175.0, icon_center_x=100.0, base_size=base, max_scale=1.65, radius=150.0)
    assert 52.0 < mid < direct


def test_spotlight_math_and_search(tmp_path: Path) -> None:
    assert evaluate_math_expression("24 * 365") == "8760"
    assert evaluate_math_expression("sqrt(256) + 4") == "20"
    assert evaluate_math_expression("hex(255)") == "0xff"

    cfg = AquaConfig(config_path=tmp_path / "settings.json")
    engine = SpotlightEngine(config=cfg)

    calc_results = engine.query("12 * 12")
    assert calc_results[0].category == "CALCULATOR"
    assert "144" in calc_results[0].title

    # Unit & currency conversions
    conv_gb = engine.query("16 GB to MB")
    assert conv_gb[0].category == "CALCULATOR"
    assert "16,384 MB" in conv_gb[0].title

    conv_curr = engine.query("100 USD to EUR")
    assert conv_curr[0].category == "CALCULATOR"
    assert "92.00 EUR" in conv_curr[0].title

    # REA binary inspection queries
    rea_results = engine.query("rea /usr/bin/python3")
    assert any(r.category == "REA" and "Deep Inspect" in r.title for r in rea_results)

    app_results = engine.query("AI Studio")
    assert any(r.category == "APPLICATION" and "Aqua AI Studio" in r.title for r in app_results)

