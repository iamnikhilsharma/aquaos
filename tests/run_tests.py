"""Zero-dependency test runner for AquaOS-Beta (works with standard library or pytest)."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent / "aqua-desktop"))

import test_ai_engine
import test_desktop
import test_security
import test_system_prefs
import test_universal


def run_all_tests() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    test_functions = [
        ("test_ai_engine.test_hardware_fit_estimator", test_ai_engine.test_hardware_fit_estimator, False),
        ("test_ai_engine.test_neural_boost_env_and_status", test_ai_engine.test_neural_boost_env_and_status, False),
        ("test_ai_engine.test_natural_language_os_intents", test_ai_engine.test_natural_language_os_intents, False),
        ("test_ai_engine.test_sandboxed_ai_code_execution", test_ai_engine.test_sandboxed_ai_code_execution, False),
        ("test_ai_engine.test_extract_code_block", test_ai_engine.test_extract_code_block, False),
        ("test_security.test_gatekeeper_clean_file_and_trust", test_security.test_gatekeeper_clean_file_and_trust, True),
        ("test_security.test_gatekeeper_malicious_payload_detection", test_security.test_gatekeeper_malicious_payload_detection, True),
        ("test_security.test_gatekeeper_rea_deep_inspect_script_and_entropy", test_security.test_gatekeeper_rea_deep_inspect_script_and_entropy, True),
        ("test_security.test_gatekeeper_rea_deep_inspect_pe_mock", test_security.test_gatekeeper_rea_deep_inspect_pe_mock, True),
        ("test_security.test_gatekeeper_rea_hexdump", test_security.test_gatekeeper_rea_hexdump, True),
        ("test_security.test_gatekeeper_rea_imports_and_exports", test_security.test_gatekeeper_rea_imports_and_exports, True),
        ("test_security.test_gatekeeper_rea_disassembly", test_security.test_gatekeeper_rea_disassembly, True),
        ("test_security.test_gatekeeper_rea_elf_sections_and_architecture", test_security.test_gatekeeper_rea_elf_sections_and_architecture, True),
        ("test_security.test_gatekeeper_rea_macho_parsing", test_security.test_gatekeeper_rea_macho_parsing, True),
        ("test_security.test_ai_engine_rea_binary_forensics", test_security.test_ai_engine_rea_binary_forensics, False),
        ("test_security.test_gatekeeper_rea_decompiler", test_security.test_gatekeeper_rea_decompiler, True),
        ("test_security.test_sandbox_bwrap_command_isolation", test_security.test_sandbox_bwrap_command_isolation, True),
        ("test_universal.test_universal_runner_formats", test_universal.test_universal_runner_formats, True),
        ("test_universal.test_universal_runner_blocks_malware", test_universal.test_universal_runner_blocks_malware, True),
        ("test_universal.test_universal_package_manager", test_universal.test_universal_package_manager, False),
        ("test_desktop.test_config_persistence", test_desktop.test_config_persistence, True),
        ("test_desktop.test_menu_bar_control_center_persisted_prefs", test_desktop.test_menu_bar_control_center_persisted_prefs, False),
        ("test_desktop.test_genie_minimize_effect_and_selector", test_desktop.test_genie_minimize_effect_and_selector, False),
        ("test_desktop.test_finder_list_view_sorting_and_dir_size_placeholder", test_desktop.test_finder_list_view_sorting_and_dir_size_placeholder, False),
        ("test_system_prefs.test_prefs_defaults_and_validation", test_system_prefs.test_prefs_defaults_and_validation, False),
        ("test_system_prefs.test_config_defaults_match_prefs_model", test_system_prefs.test_config_defaults_match_prefs_model, False),
        ("test_system_prefs.test_system_prefs_routes_persist", test_system_prefs.test_system_prefs_routes_persist, False),
        ("test_system_prefs.test_settings_tabs_routes_persist", test_system_prefs.test_settings_tabs_routes_persist, False),
        ("test_system_prefs.test_storage_usage_route", test_system_prefs.test_storage_usage_route, False),
        ("test_desktop.test_settings_panes_persisted_parity", test_desktop.test_settings_panes_persisted_parity, False),
        ("test_desktop.test_dock_parabolic_magnification", test_desktop.test_dock_parabolic_magnification, False),
        ("test_desktop.test_spotlight_math_and_search", test_desktop.test_spotlight_math_and_search, True),
        ("test_desktop.test_finder_root_directory_navigation", test_desktop.test_finder_root_directory_navigation, False),
        ("test_desktop.test_default_apps_configuration", test_desktop.test_default_apps_configuration, True),
        ("test_desktop.test_builtin_apps_indexed", test_desktop.test_builtin_apps_indexed, False),
        ("test_desktop.test_desktop_html_windows_and_resizing", test_desktop.test_desktop_html_windows_and_resizing, False),
        ("test_desktop.test_virtual_machine_scripts", test_desktop.test_virtual_machine_scripts, False),
    ]

    passed = 0
    failed = 0
    print("=" * 68)
    print("  AquaOS-Beta Automated Test Suite")
    print("=" * 68)

    for name, fn, needs_tmp in test_functions:
        tmp_dir = Path(tempfile.mkdtemp(prefix="aquaos_test_")) if needs_tmp else None
        try:
            if needs_tmp and tmp_dir is not None:
                fn(tmp_dir)
            else:
                fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {name}: {exc}")
            failed += 1
        finally:
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

    print("-" * 68)
    print(f"  Summary: {passed} passed, {failed} failed out of {len(test_functions)} tests")
    print("=" * 68)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_all_tests())
