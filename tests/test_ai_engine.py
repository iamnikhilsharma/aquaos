"""Automated tests for Aqua Intelligence (aqua-ai) & Neural Boost."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aqua-desktop"))

from ai.ai_engine import AquaAIEngine
from ai.ai_studio import extract_first_code_block
from ai.neural_boost import NeuralBoostManager


def test_hardware_fit_estimator() -> None:
    engine = AquaAIEngine()
    # Test with 16 GB RAM and 8 GB VRAM (total 24 GB unified/hybrid memory)
    fits = engine.evaluate_hardware_fit(ram_gb=16.0, vram_gb=8.0)
    assert len(fits) >= 5
    by_id = {f.model.model_id: f for f in fits}
    assert by_id["deepseek-r1:7b"].status == "FULL_GPU_OFFLOAD"
    assert by_id["gemma3:12b"].status == "FULL_GPU_OFFLOAD"
    assert by_id["deepseek-r1:32b"].status == "HYBRID_VRAM_RAM"

    # Test with 8 GB RAM and 4 GB VRAM
    low_fits = {f.model.model_id: f for f in engine.evaluate_hardware_fit(ram_gb=8.0, vram_gb=4.0)}
    assert low_fits["deepseek-r1:32b"].status == "INSUFFICIENT_MEMORY"


def test_neural_boost_env_and_status() -> None:
    mgr = NeuralBoostManager()
    status = mgr.set_neural_boost(True, flash_attention=True, kv_cache_type="q8_0")
    assert status.enabled is True
    assert status.flash_attention is True
    assert status.kv_cache_type == "q8_0"
    assert status.env_vars["OLLAMA_FLASH_ATTENTION"] == "1"
    assert status.env_vars["OLLAMA_KV_CACHE_TYPE"] == "q8_0"


def test_natural_language_os_intents() -> None:
    engine = AquaAIEngine()
    dark_res = engine.ask("Please switch to dark mode")
    assert dark_res["source"] == "os_intent"
    assert dark_res["os_action"]["action"] == "set_theme"
    assert dark_res["os_action"]["value"] == "dark"

    boost_res = engine.ask("enable neural boost for ai")
    assert boost_res["source"] == "os_intent"
    assert boost_res["os_action"]["action"] == "neural_boost"


def test_sandboxed_ai_code_execution() -> None:
    engine = AquaAIEngine()
    res = engine.execute_ai_code_safely("print(6 * 7)", language="python")
    assert res["sandboxed"] is True
    assert res["exit_code"] == 0
    assert res["stdout"] == "42"


def test_extract_code_block() -> None:
    sample = "Here is code:\n```python\nprint('hello')\n```\nDone."
    assert extract_first_code_block(sample) == "print('hello')"
