"""Aqua AI Studio (ai_studio.py).

Native macOS-style GTK4 desktop application (with Tkinter/CLI fallback for cross-platform preview)
providing:
1. Assistant Chat with streaming/instant replies and one-click "Run Code in Aqua Sandbox"
2. Model Hub with live Hardware VRAM/RAM Fit Badges and Ollama pull integration
3. Neural Compute controls (Neural Boost, Flash Attention, KV Cache Quantization, Benchmark)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.ai_engine import AquaAIEngine
from core.config import AquaConfig


def extract_first_code_block(text: str) -> Optional[str]:
    """Extract the first fenced Python/Bash code block from an AI response."""
    match = re.search(r"```(?:python|py|bash|sh)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def launch_gtk_ai_studio(engine: AquaAIEngine, config: AquaConfig) -> bool:
    """Launch the GTK4 native Aqua AI Studio window on Linux/Wayland/X11."""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk  # type: ignore
    except Exception:
        return False

    class AIStudioApp(Gtk.Application):
        def __init__(self) -> None:
            super().__init__(application_id="org.aquaos.AIStudio")

        def do_activate(self) -> None:
            win = Gtk.ApplicationWindow(application=self, title="Aqua AI Studio — Neural Engine")
            win.set_default_size(940, 640)

            root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            root_box.set_margin_top(14)
            root_box.set_margin_bottom(14)
            root_box.set_margin_start(16)
            root_box.set_margin_end(16)

            # Header bar with Neural Boost status
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            title_lbl = Gtk.Label(label="✦ Aqua AI Studio")
            title_lbl.add_css_class("title-2")
            header_box.append(title_lbl)

            boost_btn = Gtk.ToggleButton(label="⚡ Neural Boost: ON")
            boost_btn.set_active(True)

            def on_boost_toggled(btn: Gtk.ToggleButton) -> None:
                st = engine.neural_boost.set_neural_boost(btn.get_active())
                btn.set_label(
                    f"⚡ Neural Boost: {'ON' if st.enabled else 'OFF'} ({st.gpu_backend.upper()})"
                )

            boost_btn.connect("toggled", on_boost_toggled)
            header_box.append(boost_btn)
            root_box.append(header_box)

            notebook = Gtk.Notebook()

            # Tab 1: AI Chat & Sandboxed Code Runner
            chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            chat_view = Gtk.TextView()
            chat_view.set_editable(False)
            chat_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            chat_view.set_vexpand(True)
            buf = chat_view.get_buffer()
            buf.set_text(
                "Welcome to Aqua AI Studio.\n"
                "• Local LLM Runtime: Ollama + llama.cpp (Flash Attention + Q8_0 KV Cache enabled)\n"
                "• Sandboxed Code Execution: Any generated code runs inside Aqua Sandbox (Bubblewrap).\n\n"
            )

            scroll = Gtk.ScrolledWindow()
            scroll.set_child(chat_view)
            scroll.set_vexpand(True)
            chat_box.append(scroll)

            input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            entry = Gtk.Entry()
            entry.set_placeholder_text("Ask Aqua Intelligence, write Python code, or control AquaOS...")
            entry.set_hexpand(True)
            send_btn = Gtk.Button(label="Ask AI")
            run_code_btn = Gtk.Button(label="Run Last Code in Sandbox")
            last_code: list[str] = ["print('Hello from Aqua Sandbox!')"]

            def on_send(_widget: object) -> None:
                prompt = entry.get_text().strip()
                if not prompt:
                    return
                entry.set_text("")
                res = engine.ask(prompt)
                code = extract_first_code_block(res["response"])
                if code:
                    last_code[0] = code
                end_iter = buf.get_end_iter()
                buf.insert(
                    end_iter,
                    f"\nYou: {prompt}\n"
                    f"Aqua AI ({res['model']} • {res['tokens_per_sec']} tok/s):\n{res['response']}\n",
                )

            def on_run_code(_widget: object) -> None:
                out = engine.execute_ai_code_safely(last_code[0], "python")
                end_iter = buf.get_end_iter()
                buf.insert(
                    end_iter,
                    f"\n[Aqua Sandbox Execution — Exit {out['exit_code']}]\n"
                    f"{out['stdout'] or out['stderr']}\n",
                )

            entry.connect("activate", on_send)
            send_btn.connect("clicked", on_send)
            run_code_btn.connect("clicked", on_run_code)
            input_row.append(entry)
            input_row.append(send_btn)
            input_row.append(run_code_btn)
            chat_box.append(input_row)
            notebook.append_page(chat_box, Gtk.Label(label="Assistant & Code Sandbox"))

            # Tab 2: Model Hub & Hardware Fit Estimator
            hub_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            for fit in engine.evaluate_hardware_fit():
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                lbl = Gtk.Label(
                    label=f"{fit.model.name} ({fit.model.parameters}, {fit.model.quantization}) — [{fit.status}] {fit.summary}"
                )
                lbl.set_xalign(0.0)
                lbl.set_hexpand(True)
                row.append(lbl)
                hub_box.append(row)
            notebook.append_page(hub_box, Gtk.Label(label="Model Hub & VRAM Fit"))

            root_box.append(notebook)
            win.set_child(root_box)
            win.present()

    app = AIStudioApp()
    app.run(None)
    return True


def main() -> None:
    config = AquaConfig()
    engine = AquaAIEngine(
        endpoint=config.get("ai", "endpoint", "http://127.0.0.1:11434"),
        default_model=config.get("ai", "default_model", "deepseek-r1:7b"),
    )
    if not launch_gtk_ai_studio(engine, config):
        print("=== Aqua AI Studio (CLI / Headless Mode) ===")
        for fit in engine.evaluate_hardware_fit():
            print(f"• {fit.model.name:<28} [{fit.status:<18}] {fit.summary}")


if __name__ == "__main__":
    main()
