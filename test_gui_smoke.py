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


def test_app_renders_drawings_on_canvas():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tkinter недоступен без дисплея")
    root.withdraw()
    app = App(root)
    try:
        app._set_editor("point(10, 10); line(0, 0, 100, 100);")
        app.compile()
        app.session.run_all()
        app._refresh()
        root.update_idletasks()
        assert len(app.screen_canvas.find_all()) >= 2
    finally:
        app.close()


def test_app_input_dialog_feeds_machine(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tkinter недоступен без дисплея")
    root.withdraw()
    app = App(root)
    try:
        app._set_editor(
            'string name = input("Имя: "); print("Привет,", name);'
        )
        app.compile()
        monkeypatch.setattr(
            "gui.app.simpledialog.askstring", lambda *args, **kwargs: "Аня"
        )
        app.step()      # PUSH "Имя: "
        app.step()      # INPUT: диалог и подстановка строки
        app.session.run_all()
        assert app.session.output == ["Имя: ", "Привет, Аня"]
        assert app.session.status == "finished"
    finally:
        app.close()


def test_app_max_speed_without_delay():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tkinter недоступен без дисплея")
    root.withdraw()
    app = App(root)
    try:
        app.speed_var.set("Максимум")
        assert app._steps_per_tick() > 1
        assert app._tick_delay() == 0

        app.speed_var.set("Быстро")
        assert app._steps_per_tick() == 15
        assert app._tick_delay() > 0
    finally:
        app.close()


def test_app_panel_visibility_toggle():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tkinter недоступен без дисплея")
    root.withdraw()
    app = App(root)
    try:
        app._set_panel_visible("stack", False)
        assert app._panels_visible["stack"] is False
        app._set_panel_visible("stack", True)
        assert app._panels_visible["stack"] is True
    finally:
        app.close()
