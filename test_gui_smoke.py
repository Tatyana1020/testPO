import tkinter as tk

import pytest

from gui.app import App


def test_app_smoke_compiles_steps_and_resets():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tkinter недоступен без дисплея")
    root.withdraw()
    app = App(root)
    try:
        app.compile()
        assert app.session.code
        app.step()
        assert app.session.machine is not None
        app.reset()
        assert app.session.status == "ready"
        assert app.session.machine.variables == {}
        root.update_idletasks()
    finally:
        app.close()


def test_app_expression_mode():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tkinter недоступен без дисплея")
    root.withdraw()
    app = App(root)
    try:
        app.mode_var.set("Выражение")
        app.editor.delete("1.0", "end")
        app.editor.insert("1.0", "2 ^ 10")
        app._loading = False
        app._sync_source()
        assert app.session.compile()
        assert app.session.run_all() == 1024
    finally:
        app.close()
