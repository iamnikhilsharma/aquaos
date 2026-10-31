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


def test_finder_root_directory_navigation() -> None:
    root = Path(__file__).resolve().parents[1]
    from ai.ai_engine import AquaAIEngine
    from core.linux_env import AquaLinuxEnvironment
    from security.shield_center import ShieldDiagnostics
    from universal.aqua_pkg import AquaPackageManager
    from universal.aqua_run import AquaUniversalRunner

    env = AquaLinuxEnvironment(
        project_root=root,
        telemetry_fn=lambda: {"cpu_cores": 4, "cpu_model": "Intel64", "ram_total_gb": 16.0, "ram_avail_gb": 8.0},
        ai_engine=AquaAIEngine(),
        shield_diag=ShieldDiagnostics(),
        universal_runner=AquaUniversalRunner(),
        pkg_manager=AquaPackageManager(),
    )

    # 1. Root / must list actual Linux RootFS and NOT redirect to /home/aqua/AquaOS-Beta
    res_root = env.list_linux_directory("/")
    assert res_root["current_dir"] == "/", f"Expected '/', got {res_root['current_dir']}"
    assert res_root["parent_dir"] == "/"
    names = {e["name"] for e in res_root["entries"]}
    for expected in ("bin", "boot", "dev", "etc", "home", "lib", "opt", "proc", "root", "run", "sbin", "sys", "tmp", "usr", "var"):
        assert expected in names, f"Expected {expected} in RootFS directory listing"

    # 2. Aliases ('root', 'rootfs', 'AquaOS HD', 'hd') must resolve to '/'
    for alias in ("root", "rootfs", "AquaOS HD", "hd", "ROOT"):
        _, norm = env.to_host_path(alias)
        assert norm == "/", f"Alias {alias} expected to resolve to '/', got {norm}"

    # 3. Subdirectories of root must retain correct parent and paths
    res_etc = env.list_linux_directory("/etc")
    assert res_etc["current_dir"] == "/etc"
    assert res_etc["parent_dir"] == "/"
    etc_names = {e["name"] for e in res_etc["entries"]}
    assert "os-release" in etc_names
    assert "fstab" in etc_names

    res_proc = env.list_linux_directory("/proc")
    assert res_proc["current_dir"] == "/proc"
    assert res_proc["parent_dir"] == "/"
    proc_names = {e["name"] for e in res_proc["entries"]}
    assert "cpuinfo" in proc_names
    assert "meminfo" in proc_names

    # 4. /home must list aqua user directory
    res_home = env.list_linux_directory("/home")
    assert res_home["current_dir"] == "/home"
    assert res_home["parent_dir"] == "/"
    assert any(e["name"] == "aqua" for e in res_home["entries"])

    # 5. /home/aqua must list AquaOS-Beta
    res_aqua = env.list_linux_directory("/home/aqua")
    assert res_aqua["current_dir"] == "/home/aqua"
    assert res_aqua["parent_dir"] == "/home"
    assert any(e["name"] == "AquaOS-Beta" for e in res_aqua["entries"])


def test_default_apps_configuration(tmp_path: Path) -> None:
    cfg = AquaConfig(config_path=tmp_path / "settings.json")
    defaults = cfg.get("default_apps")
    assert isinstance(defaults, dict)
    assert defaults["browser"] == "firefox"
    assert defaults["email"] == "thunderbird"
    assert defaults["image_viewer"] == "preview"
    assert defaults["music_player"] == "music"
    assert defaults["video_player"] == "quicktime"
    assert defaults["package_manager"] == "snap-store"


def test_builtin_apps_indexed() -> None:
    indexer = AppIndexer()
    apps = indexer.list_apps()
    names = {app.name for app in apps}
    expected = {"Finder", "Terminal", "Aqua AI Studio", "Aqua Shield", "Activity Monitor", "Firefox", "Thunderbird", "Snap Store", "Music", "QuickTime Player", "Preview"}
    for exp in expected:
        assert exp in names, f"Expected {exp} to be indexed in BUILTIN_AQUA_APPS"

    # Verify command execution strings
    ff = next(a for a in apps if a.name == "Firefox")
    assert "firefox" in ff.exec_cmd
    tb = next(a for a in apps if a.name == "Thunderbird")
    assert "thunderbird" in tb.exec_cmd
    store = next(a for a in apps if a.name == "Snap Store")
    assert "snap-store" in store.exec_cmd


def test_desktop_html_windows_and_resizing() -> None:
    html_path = Path(__file__).resolve().parents[1] / "aqua-desktop" / "ui" / "desktop.html"
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")

    # 1. All 13 desktop windows must exist and have class="aqua-window hidden"
    expected_windows = [
        "win-finder", "win-terminal", "win-ai", "win-shield", "win-activity", "win-settings", "win-about",
        "win-firefox", "win-preview", "win-music", "win-video", "win-thunderbird", "win-store"
    ]
    for win_id in expected_windows:
        assert f'id="{win_id}"' in content, f"Window {win_id} not found in desktop.html"
        assert f'class="aqua-window hidden" id="{win_id}"' in content or f'id="{win_id}"' in content
        # Ensure hidden class is present on the window section tag
        start_idx = content.find(f'id="{win_id}"')
        tag_start = content.rfind('<section', 0, start_idx)
        tag_end = content.find('>', start_idx)
        tag = content[tag_start:tag_end]
        assert "hidden" in tag, f"Window {win_id} must have 'hidden' class on boot: {tag}"

    # 2. Universal 8-way resize handle system must be present
    for d in ("n", "s", "e", "w", "nw", "ne", "sw", "se"):
        assert f".win-resize-{d}" in content, f"Resize handle class .win-resize-{d} missing"
    assert "initWindowResizeHandles" in content
    assert "startWindowResize" in content

    # 3. Default applications, media players, and snap store scripts must be present
    assert "navigateFirefox" in content
    assert "previewOpenFile" in content
    assert "toggleMusicPlay" in content
    assert "toggleVideoPlayback" in content
    assert "switchTbFolder" in content
    assert "installSnapPackage" in content


def test_genie_minimize_effect_and_selector() -> None:
    """Genie minimize effect (warp to dock) + Genie/Scale selector in Dock settings."""
    html_path = Path(__file__).resolve().parents[1] / "aqua-desktop" / "ui" / "desktop.html"
    content = html_path.read_text(encoding="utf-8")

    # 1. Genie warp keyframes and animation classes are present
    assert "@keyframes aqua-genie-out" in content
    assert "@keyframes aqua-genie-in" in content
    assert ".aqua-window.genie-min" in content
    assert ".aqua-window.genie-restore" in content

    # 2. Genie/Scale "Minimize Effect" selector exists in the Dock settings pane
    assert 'id="btn-min-effect-scale"' in content
    assert 'id="btn-min-effect-genie"' in content
    assert "setMinimizeEffect('scale')" in content
    assert "setMinimizeEffect('genie')" in content

    # 3. Effect state + persistence plumbing (localStorage key aquaos_min_effect)
    assert "let minimizeEffect = 'scale';" in content
    assert "aquaos_min_effect" in content

    # 4. minimizeWindow honors the choice (genie warp vs classic hidden shrink)
    assert "if (minimizeEffect === 'genie') {" in content
    assert "classList.add('hidden', 'genie-min')" in content
    assert "playGenieAnimation(win, true)" in content

    # 5. openWindow replays the warp in reverse when restoring a genie-minimized window
    assert "contains('genie-min')" in content
    assert "classList.add('genie-restore')" in content
    assert "playGenieAnimation(win, false)" in content

    # 6. Dock items expose their window mapping for genie suction targets
    dock_ids = [
        "win-finder", "win-terminal", "win-ai", "win-shield", "win-activity", "win-settings",
        "win-firefox", "win-thunderbird", "win-store", "win-music", "win-video", "win-preview", "win-about",
    ]
    for wid in dock_ids:
        assert f'class="dock-item" data-win="{wid}"' in content, f"dock-item data-win mapping for {wid} missing"


def test_virtual_machine_scripts() -> None:
    root = Path(__file__).resolve().parents[1]
    ps1_script = root / "scripts" / "run-vm.ps1"
    bat_script = root / "scripts" / "run-vm.bat"
    vm_doc = root / "docs" / "VIRTUAL_MACHINE.md"

    assert ps1_script.exists(), "scripts/run-vm.ps1 must exist"
    assert bat_script.exists(), "scripts/run-vm.bat must exist"
    assert vm_doc.exists(), "docs/VIRTUAL_MACHINE.md must exist"

    ps1_text = ps1_script.read_text(encoding="utf-8")
    assert "qemu-system-x86_64" in ps1_text
    assert "whpx" in ps1_text
    assert "8765" in ps1_text
    assert "2222" in ps1_text
    assert "dist" in ps1_text

    doc_text = vm_doc.read_text(encoding="utf-8")
    assert "QEMU" in doc_text
    assert "VirtualBox" in doc_text
    assert "VMware" in doc_text


def test_finder_list_view_sorting_and_dir_size_placeholder() -> None:
    """Finder List view parity: click-to-sort column headers (Name, Date Modified, Size,
    Kind in macOS order) that toggle asc/desc and persist across directory navigations,
    plus the macOS-style '—' placeholder replacing the hardcoded '4.0 KB (dir)'."""
    html_path = Path(__file__).resolve().parents[1] / "aqua-desktop" / "ui" / "desktop.html"
    content = html_path.read_text(encoding="utf-8")

    # 1. Sort state + engine: default Name ascending; re-applied on every directory
    #    render so the sort choice persists across browseTo/navigate/refresh.
    assert "let finderSort = { key: 'name', dir: 'asc' };" in content
    assert "function sortFinderEntries(" in content
    assert "function sortFinderBy(" in content
    assert "currentFsEntries = sortFinderEntries(fsData.entries || []);" in content
    # Repeated click on the same header toggles asc -> desc -> asc
    assert "finderSort.key === key ? (finderSort.dir === 'asc' ? 'desc' : 'asc') : 'asc'" in content
    # Folders stay on top under every sort key (macOS 'Keep folders on top')
    assert "if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;" in content

    # 2. Sortable headers exist for all four keys, in macOS column order
    i_name = content.find("sortFinderBy('name')")
    i_mtime = content.find("sortFinderBy('mtime')")
    i_size = content.find("sortFinderBy('size')")
    i_kind = content.find("sortFinderBy('kind')")
    assert 0 < i_name < i_mtime < i_size < i_kind, "Headers must appear in macOS order: Name, Date Modified, Size, Kind"
    assert 'data-sort-key="name"' in content
    assert 'data-sort-key="mtime"' in content
    assert 'data-sort-key="size"' in content
    assert 'data-sort-key="kind"' in content

    # 3. Sort direction indicators (▲ ascending / ▼ descending) on the active column
    assert "function updateSortIndicators(" in content
    assert "fs-sort-arrow" in content
    assert "'▲' : '▼'" in content

    # 4. Kind column backed by a shared kind classifier
    assert "function finderItemKind(" in content
    assert "return 'Python Script';" in content
    assert "return 'Folder';" in content

    # 5. The macOS '—' folder-size placeholder replaces the hardcoded value in every
    #    surface that displays a directory size: list rows, Miller preview, Gallery inspector.
    assert "4.0 KB" not in content, "Folder size must no longer hardcode '4.0 KB (dir)'"
    assert "sizeStr = item.is_dir ? '—' :" in content, "List-view rows must show '—' for folders"
    assert "item.is_dir ? '—' : item.size_kb + ' KB'" in content, "Gallery inspector must show '—' for folders"
    assert "isDir ? '—' : item.size_kb + ' KB'" in content, "Miller columns preview must show '—' for folders"

    # 6. Row rendering factors into renderFsListRows so sorting can re-render the
    #    table without refetching, and renderDirectory calls it on every load.
    assert "function renderFsListRows(" in content
    assert content.count("renderFsListRows();") >= 2, "renderDirectory and sortFinderBy must both re-render rows"

    # 7. Switching directly into Gallery View (⌘4) must reveal and render it
    #    immediately — not only after the next directory navigation (parity with
    #    the Icons/Columns branches, which render on switch).
    assert "if (galleryEl) { galleryEl.style.display = 'flex'; renderGalleryView(); }" in content, \
        "setFinderView('gallery') must show #fs-gallery-view and call renderGalleryView()"


def test_menu_bar_control_center_persisted_prefs() -> None:
    """Menu Bar & Control Center expansion: Night Shift, the input-source switcher,
    and battery power mode are wired to real endpoints with persisted state."""
    html_path = Path(__file__).resolve().parents[1] / "aqua-desktop" / "ui" / "desktop.html"
    content = html_path.read_text(encoding="utf-8")

    # 1. Night Shift: single source of truth, shared across CC button + Displays toggle,
    #    persisted through /api/system/night-shift
    assert "let nightShiftActive = false;" in content
    assert "function applyNightShift(active)" in content
    assert "function setNightShift(active)" in content
    assert content.count("/api/system/night-shift") >= 1
    assert "JSON.stringify({enabled: active})" in content
    assert 'id="toggle-night-shift" onclick="setNightShift(!nightShiftActive)"' in content
    assert 'id="btn-cc-nightshift" style="padding:2px 8px; font-size:10.5px;" onclick="setNightShift(!nightShiftActive)"' in content
    # Stale cosmetic handlers must be gone (toast-only / filter inference)
    assert "function toggleNightShift(el)" not in content
    assert "style.filter.includes('sepia')" not in content

    # 2. Input-source switcher in the Keyboard pane — three canonical options
    i_us = content.find("setInputSource('US')")
    i_intl = content.find("setInputSource('International')")
    i_dvorak = content.find("setInputSource('Dvorak')")
    assert 0 < i_us < i_intl < i_dvorak, "Input-source buttons must exist in macOS order"
    assert 'id="btn-input-US"' in content
    assert 'id="btn-input-International"' in content
    assert 'id="btn-input-Dvorak"' in content
    assert "const INPUT_SOURCES = ['US', 'International', 'Dvorak'];" in content
    assert "function setInputSource(source)" in content
    assert "/api/system/input-source" in content
    assert "JSON.stringify({source})" in content

    # 3. Battery power mode: Settings select + menu-bar Low Power toggle share it
    assert 'id="sel-power-mode"' in content
    assert 'onchange="setPowerMode(this.value)"' in content
    assert "const POWER_MODES = ['Automatic', 'Low Power Mode', 'High Power Mode'];" in content
    assert "function applyPowerMode(mode)" in content
    assert "function setPowerMode(mode)" in content
    assert "/api/system/power-mode" in content
    assert "JSON.stringify({mode})" in content
    assert 'id="bat-lpm-toggle"' in content
    assert "setPowerMode(enabling ? 'Low Power Mode' : 'Automatic')" in content

    # 4. Persisted state is restored on boot from /api/settings/get
    assert "function loadPersistedPrefs()" in content
    assert "'/api/settings/get'" in content
    assert "loadPersistedPrefs();" in content


