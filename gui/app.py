from __future__ import annotations

import ctypes
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .controller import (
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    DebugSession,
    format_instruction,
)
from .examples import EXAMPLES

MODE_LABELS = {"Программа": "program", "Выражение": "expression"}
STATUS_LABELS = {
    "ready": "готова",
    "paused": "пауза",
    "running": "выполняется",
    "waiting": "ожидание горутин",
    "waiting_input": "ждёт ввода",
    "finished": "завершено",
    "error": "ошибка",
}


def enable_dpi_awareness() -> None:
    """Включить нативное масштабирование Windows до создания Tk-окна.

    Без этого Windows считает приложение DPI-независимым только формально
    и растягивает готовую картинку окна, из-за чего шрифт выглядит мыльным.
    """
    if sys.platform != "win32":
        return
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(1) == 0:
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def apply_tk_scaling(root: tk.Tk) -> None:
    """Согласовать pt-размеры Tk с реальным DPI монитора."""
    if sys.platform != "win32":
        return
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
    except tk.TclError:
        pass


class App:
    """Tkinter-представление. Вся логика — в DebugSession."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Stack Lang — визуализатор")
        self.root.geometry("1280x820")
        self.root.minsize(900, 600)

        self.session = DebugSession()
        self._after_id: str | None = None
        self._loading = False
        self._path: Path | None = None
        self._last_status = ""
        self._shown_output = 0
        self._screen_generation = -1
        self._screen_count = 0
        self._screen_auto_show = True
        self._color_cache: dict[str, str] = {}

        self.mode_var = tk.StringVar(value="Программа")
        self.speed_var = tk.StringVar(value="Обычно")
        self.example_var = tk.StringVar(value=next(iter(EXAMPLES)))
        self.status_var = tk.StringVar(value="Готово")

        self._setup_style()
        self._build_toolbar()
        self._build_main()
        self._build_output()
        self._build_statusbar()
        self._bind_shortcuts()

        self._load_example(next(iter(EXAMPLES)))
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ------------------------------------------------------------------
    # построение интерфейса
    # ------------------------------------------------------------------

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        line_height = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        style.configure("Treeview", rowheight=line_height + 6)
        style.configure("Status.TLabel", padding=(6, 3))

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(8, 6))
        bar.pack(fill="x")

        ttk.Label(bar, text="Режим:").pack(side="left")
        mode = ttk.Combobox(
            bar,
            textvariable=self.mode_var,
            values=("Программа", "Выражение"),
            state="readonly",
            width=12,
        )
        mode.pack(side="left", padx=(4, 12))
        mode.bind("<<ComboboxSelected>>", self._on_mode_changed)

        ttk.Button(bar, text="Компилировать", command=self.compile).pack(
            side="left", padx=2
        )
        ttk.Button(bar, text="Запуск", command=self.run).pack(side="left", padx=2)
        ttk.Button(bar, text="Пауза", command=self.pause).pack(side="left", padx=2)
        ttk.Button(bar, text="Шаг", command=self.step).pack(side="left", padx=2)
        ttk.Button(bar, text="Сброс", command=self.reset).pack(side="left", padx=2)

        ttk.Separator(bar, orient="vertical").pack(
            side="left", fill="y", padx=8, pady=2
        )
        ttk.Label(bar, text="Скорость:").pack(side="left")
        speed = ttk.Combobox(
            bar,
            textvariable=self.speed_var,
            values=("Медленно", "Обычно", "Быстро"),
            state="readonly",
            width=10,
        )
        speed.pack(side="left", padx=(4, 12))

        ttk.Label(bar, text="Пример:").pack(side="left")
        example = ttk.Combobox(
            bar,
            textvariable=self.example_var,
            values=tuple(EXAMPLES),
            state="readonly",
            width=18,
        )
        example.pack(side="left", padx=4)
        example.bind("<<ComboboxSelected>>", self._on_example_changed)

        ttk.Button(bar, text="Открыть", command=self.open_file).pack(
            side="right", padx=2
        )
        ttk.Button(bar, text="Сохранить", command=self.save_file).pack(
            side="right", padx=2
        )

    def _build_main(self) -> None:
        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        left = ttk.Frame(main)
        main.add(left, weight=3)

        ttk.Label(left, text="Исходник").pack(anchor="w")
        editor_frame = ttk.Frame(left)
        editor_frame.pack(fill="both", expand=True)
        self.editor = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            font=("Consolas", 11),
            padx=8,
            pady=6,
        )
        editor_scroll = ttk.Scrollbar(
            editor_frame, orient="vertical", command=self.editor.yview
        )
        self.editor.configure(yscrollcommand=editor_scroll.set)
        self.editor.pack(side="left", fill="both", expand=True)
        editor_scroll.pack(side="right", fill="y")
        self.editor.tag_configure("current_line", background="#fff2b2")
        self.editor.tag_configure("error_line", background="#ffd3d3")
        self.editor.bind("<<Modified>>", self._on_source_modified)

        right = ttk.Panedwindow(main, orient="vertical")
        main.add(right, weight=4)

        self.view_tabs = ttk.Notebook(right)
        right.add(self.view_tabs, weight=3)
        self.screen_tab_index = 1

        code_frame = ttk.Frame(self.view_tabs)
        self.view_tabs.add(code_frame, text="Байт-код")
        self.code_tree = ttk.Treeview(
            code_frame,
            columns=("pc", "op", "arg", "line"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width, anchor in (
            ("pc", "PC", 60, "e"),
            ("op", "Операция", 110, "w"),
            ("arg", "Аргумент", 180, "w"),
            ("line", "Строка", 70, "e"),
        ):
            self.code_tree.heading(column, text=title)
            self.code_tree.column(column, width=width, anchor=anchor, stretch=False)
        code_scroll = ttk.Scrollbar(
            code_frame, orient="vertical", command=self.code_tree.yview
        )
        self.code_tree.configure(yscrollcommand=code_scroll.set)
        self.code_tree.pack(side="left", fill="both", expand=True)
        code_scroll.pack(side="right", fill="y")
        self.code_tree.tag_configure("current", background="#fff1a8")
        self.code_tree.tag_configure("breakpoint", foreground="#b00020")
        self.code_tree.bind("<Double-1>", self._toggle_breakpoint)
        self.code_tree.bind("<<TreeviewSelect>>", self._on_code_select)

        self.screen_tab = ttk.Frame(self.view_tabs)
        self.view_tabs.add(self.screen_tab, text="Экран")
        self._build_screen(self.screen_tab)

        bottom = ttk.Panedwindow(right, orient="horizontal")
        right.add(bottom, weight=2)

        stack_frame = ttk.LabelFrame(bottom, text="Стек (вершина сверху)")
        bottom.add(stack_frame, weight=1)
        self.stack_tree = ttk.Treeview(
            stack_frame,
            columns=("index", "value"),
            show="headings",
        )
        self.stack_tree.heading("index", text="Индекс")
        self.stack_tree.heading("value", text="Значение")
        self.stack_tree.column("index", width=70, anchor="e", stretch=False)
        self.stack_tree.column("value", width=150, anchor="w")
        stack_scroll = ttk.Scrollbar(
            stack_frame, orient="vertical", command=self.stack_tree.yview
        )
        self.stack_tree.configure(yscrollcommand=stack_scroll.set)
        self.stack_tree.pack(side="left", fill="both", expand=True)
        stack_scroll.pack(side="right", fill="y")
        self.stack_tree.tag_configure("top", background="#dff0d8")

        goroutines_frame = ttk.LabelFrame(bottom, text="Горутины")
        bottom.add(goroutines_frame, weight=1)
        self.goroutines_tree = ttk.Treeview(
            goroutines_frame,
            columns=("name", "status", "steps"),
            show="headings",
        )
        self.goroutines_tree.heading("name", text="Имя")
        self.goroutines_tree.heading("status", text="Состояние")
        self.goroutines_tree.heading("steps", text="Шагов")
        self.goroutines_tree.column("name", width=110, anchor="w")
        self.goroutines_tree.column("status", width=110, anchor="w")
        self.goroutines_tree.column("steps", width=60, anchor="e", stretch=False)
        goroutines_scroll = ttk.Scrollbar(
            goroutines_frame, orient="vertical", command=self.goroutines_tree.yview
        )
        self.goroutines_tree.configure(yscrollcommand=goroutines_scroll.set)
        self.goroutines_tree.pack(side="left", fill="both", expand=True)
        goroutines_scroll.pack(side="right", fill="y")

        variables_frame = ttk.LabelFrame(bottom, text="Переменные")
        bottom.add(variables_frame, weight=1)
        self.variables_tree = ttk.Treeview(
            variables_frame,
            columns=("name", "type", "value"),
            show="headings",
        )
        self.variables_tree.heading("name", text="Имя")
        self.variables_tree.heading("type", text="Тип")
        self.variables_tree.heading("value", text="Значение")
        self.variables_tree.column("name", width=120, anchor="w")
        self.variables_tree.column("type", width=70, anchor="w")
        self.variables_tree.column("value", width=150, anchor="w")
        variables_scroll = ttk.Scrollbar(
            variables_frame, orient="vertical", command=self.variables_tree.yview
        )
        self.variables_tree.configure(yscrollcommand=variables_scroll.set)
        self.variables_tree.pack(side="left", fill="both", expand=True)
        variables_scroll.pack(side="right", fill="y")

    def _build_screen(self, parent: ttk.Frame) -> None:
        hint = ttk.Label(
            parent,
            text=f"{SCREEN_WIDTH}×{SCREEN_HEIGHT}, (0,0) — левый верхний угол",
            anchor="w",
            font=("TkDefaultFont", 8),
            wraplength=240,
        )
        hint.pack(side="bottom", fill="x", pady=(2, 0))
        self.screen_canvas = tk.Canvas(
            parent,
            background="white",
            highlightthickness=1,
            highlightbackground="#c8c8c8",
        )
        self.screen_canvas.pack(fill="both", expand=True, pady=(2, 4))
        self.screen_canvas.bind("<Configure>", self._on_screen_resize)

    def _build_output(self) -> None:
        frame = ttk.LabelFrame(self.root, text="Вывод")
        frame.pack(fill="both", padx=8, pady=(0, 4))
        self.output = tk.Text(
            frame,
            height=7,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            padx=6,
            pady=4,
        )
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        self.output.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.output.tag_configure("info", foreground="#222222")
        self.output.tag_configure("success", foreground="#1b6e1b")
        self.output.tag_configure("warn", foreground="#9a6700")
        self.output.tag_configure("error", foreground="#b00020")

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", side="bottom")
        ttk.Label(
            bar, textvariable=self.status_var, style="Status.TLabel", anchor="w"
        ).pack(fill="x")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<F5>", lambda _event: self.run())
        self.root.bind("<F6>", lambda _event: self.pause())
        self.root.bind("<F10>", lambda _event: self.step())
        self.root.bind("<Control-Return>", lambda _event: self.compile())
        self.root.bind("<Control-r>", lambda _event: self.reset())

    # ------------------------------------------------------------------
    # действия
    # ------------------------------------------------------------------

    def compile(self) -> None:
        self._stop_timer()
        self._sync_source()
        self._clear_output()
        self._clear_highlights()
        self._last_status = ""
        self._screen_auto_show = True
        if self.session.compile():
            count = len(self.session.code or [])
            self._log(f"Скомпилировано инструкций: {count}", "success")
        else:
            self._show_error()
        self._refresh()

    def run(self) -> None:
        if self._after_id is not None:
            self.pause()
            return
        if not self._ensure_compiled():
            return
        if self.session.machine is None:
            return
        if self.session.machine.status in ("finished", "error"):
            self.session.reset()
        elif self.session.machine.status == "ready":
            # Запуск после остановки на начальной точке — это новый запуск.
            self._screen_auto_show = True
        self._clear_output()
        self._log("Запуск", "info")
        self.session.resume()
        self._last_status = ""
        self._tick()

    def pause(self) -> None:
        if self._after_id is not None:
            self._stop_timer()
            self._log("Пауза", "warn")
            self._refresh()

    def step(self) -> None:
        self._stop_timer()
        if not self._ensure_compiled() or self.session.machine is None:
            return
        if self.session.machine.status in ("finished", "error"):
            self.session.reset()
            self._last_status = ""
        self.session.step()
        self._refresh()
        if self.session.status == "error":
            self._show_error()
            return
        if self.session.waiting_for_input:
            if self._request_input():
                self.session.step()
                self._refresh()
            if self.session.status == "error":
                self._show_error()
                return
            self._announce_if_finished()
            return
        self._announce_if_finished()

    def _request_input(self) -> bool:
        """Спросить строку для ``input()``; False — пользователь отменил."""
        if not self.session.waiting_for_input:
            return True
        prompt = self.session.input_prompt or "Введите строку:"
        value = simpledialog.askstring("Ввод", prompt, parent=self.root)
        if value is None:
            self._log("Ввод отменён", "warn")
            return False
        self._log(f"> {value}", "info")
        return self.session.provide_input(value)

    def reset(self) -> None:
        self._stop_timer()
        self._screen_auto_show = True
        if self.session.machine is None:
            self.compile()
            return
        self.session.reset()
        self._clear_output()
        self._log("Сброс", "info")
        self._last_status = ""
        self._refresh()

    def _tick(self) -> None:
        self._after_id = None
        if self.session.machine is None:
            return
        if self.session.at_breakpoint():
            self._log(
                f"Остановка: точка останова PC {self.session.machine.pc}", "warn"
            )
            self._refresh()
            return

        for _ in range(self._steps_per_tick()):
            if not self.session.step():
                break
        self._refresh()
        if self.session.status == "error":
            self._show_error()
            return
        if self.session.waiting_for_input:
            if self._request_input():
                self._after_id = self.root.after(self._tick_delay(), self._tick)
            return
        if self.session.status == "finished":
            self._announce_if_finished()
            return
        self._after_id = self.root.after(self._tick_delay(), self._tick)

    def _ensure_compiled(self) -> bool:
        self._sync_source()
        if not self.session.ensure_compiled():
            self._clear_output()
            self._show_error()
            self._refresh()
            return False
        return True

    def _steps_per_tick(self) -> int:
        return {"Медленно": 1, "Обычно": 2, "Быстро": 15}.get(
            self.speed_var.get(), 2
        )

    def _tick_delay(self) -> int:
        return {"Медленно": 250, "Обычно": 80, "Быстро": 15}.get(
            self.speed_var.get(), 80
        )

    def _announce_if_finished(self) -> None:
        if self.session.machine is None:
            return
        if self.session.machine.status != "finished":
            return
        if self._last_status == "finished":
            return
        self._last_status = "finished"
        if self.session.mode == "expression":
            self._log(f"Результат: {self.session.machine.result}", "success")
        else:
            variables = self.session.snapshot()["variables"]
            rendered = ", ".join(f"{k}={v}" for k, v in sorted(variables.items()))
            self._log(f"Переменные: {rendered or 'нет'}", "success")

    def _show_error(self) -> None:
        message = self.session.error
        if message:
            self._log(message, "error")
            self._highlight_error(self.session.error_line)

    # ------------------------------------------------------------------
    # обновление представления
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        self._flush_output()
        self._refresh_code()
        self._refresh_screen()
        self._refresh_stack()
        self._refresh_variables()
        self._refresh_goroutines()
        self._update_status()
        line = self.session.current_line()
        if self.session.status != "error":
            self._highlight_source_line(line)

    def _refresh_code(self) -> None:
        self.code_tree.delete(*self.code_tree.get_children())
        code = self.session.code or []
        lines = self.session.lines
        current = self.session.machine.pc if self.session.machine else None
        for pc, instruction in enumerate(code):
            op, *args = instruction
            rendered = " ".join(str(arg) for arg in args)
            tags = []
            if pc in self.session.breakpoints:
                tags.append("breakpoint")
            if current is not None and pc == current:
                tags.append("current")
            line = lines[pc] if pc < len(lines) else ""
            self.code_tree.insert(
                "",
                "end",
                iid=str(pc),
                values=(pc, op, rendered, line),
                tags=tuple(tags),
            )
        if current is not None and 0 <= current < len(code):
            self.code_tree.see(str(current))

    def _refresh_screen(self) -> None:
        """Дорисовать команды, появившиеся с прошлого обновления."""
        generation, count = self.session.drawings_revision
        if (
            generation != self._screen_generation
            or count < self._screen_count
        ):
            # Полная перерисовка: новый запуск, сброс машины или resize.
            self._screen_generation = generation
            self._screen_count = count
            self._render_drawings(self.session.drawings, reset=True)
            if count and self._screen_auto_show:
                self._show_screen_tab()
            return
        if count == self._screen_count:
            return
        drawings = self.session.drawings
        pending = drawings[self._screen_count :]
        self._screen_count = count
        self._render_drawings(pending, reset=False)
        if self._screen_auto_show:
            self._show_screen_tab()

    def _show_screen_tab(self) -> None:
        """Показать холст при первом рисунке нового запуска."""
        self._screen_auto_show = False
        if self.view_tabs.select() != str(self.screen_tab):
            self.view_tabs.select(self.screen_tab)

    def _on_screen_resize(self, _event=None) -> None:
        self._screen_generation = -1
        self._refresh_screen()

    def _resolve_color(self, color: str) -> str:
        """Проверить цвет средствами Tk и заменить неизвестный на чёрный."""
        cached = self._color_cache.get(color)
        if cached is not None:
            return cached
        try:
            self.screen_canvas.winfo_rgb(color)
            resolved = color
        except tk.TclError:
            resolved = "black"
        self._color_cache[color] = resolved
        return resolved

    def _render_drawings(self, drawings: list[dict], reset: bool) -> None:
        canvas = self.screen_canvas
        if reset:
            canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            width, height = SCREEN_WIDTH, SCREEN_HEIGHT
        scale = min(width / SCREEN_WIDTH, height / SCREEN_HEIGHT)
        if scale <= 0:
            return
        offset_x = (width - SCREEN_WIDTH * scale) / 2
        offset_y = (height - SCREEN_HEIGHT * scale) / 2

        def screen_x(x: float) -> float:
            return offset_x + x * scale

        def screen_y(y: float) -> float:
            return offset_y + y * scale

        for command in drawings:
            op = command["op"]
            if op == "clear":
                canvas.delete("all")
                continue
            color = self._resolve_color(str(command.get("color", "black")))
            line_width = max(1, round(command.get("width", 2) * scale))
            try:
                if op == "point":
                    x = screen_x(command["x"])
                    y = screen_y(command["y"])
                    radius = max(2.0, line_width / 2.0)
                    canvas.create_oval(
                        x - radius,
                        y - radius,
                        x + radius,
                        y + radius,
                        fill=color,
                        outline=color,
                    )
                elif op == "line":
                    canvas.create_line(
                        screen_x(command["x1"]),
                        screen_y(command["y1"]),
                        screen_x(command["x2"]),
                        screen_y(command["y2"]),
                        fill=color,
                        width=line_width,
                    )
                elif op == "rect":
                    canvas.create_rectangle(
                        screen_x(command["x1"]),
                        screen_y(command["y1"]),
                        screen_x(command["x2"]),
                        screen_y(command["y2"]),
                        outline=color,
                        width=line_width,
                    )
                elif op == "circle":
                    x = screen_x(command["x"])
                    y = screen_y(command["y"])
                    radius = command["r"] * scale
                    canvas.create_oval(
                        x - radius,
                        y - radius,
                        x + radius,
                        y + radius,
                        outline=color,
                        width=line_width,
                    )
                elif op == "text":
                    canvas.create_text(
                        screen_x(command["x"]),
                        screen_y(command["y"]),
                        text=command["text"],
                        fill=color,
                        anchor="nw",
                        font=("TkDefaultFont", max(7, round(12 * scale))),
                    )
            except tk.TclError:
                # Некорректная координата или цвет не должны ронять GUI.
                continue

    def _refresh_stack(self) -> None:
        self.stack_tree.delete(*self.stack_tree.get_children())
        if self.session.machine is None:
            return
        stack = self.session.machine.stack
        for index, value in reversed(list(enumerate(stack))):
            tags = ("top",) if index == len(stack) - 1 else ()
            self.stack_tree.insert(
                "", "end", iid=f"s{index}", values=(index, value), tags=tags
            )

    def _refresh_goroutines(self) -> None:
        self.goroutines_tree.delete(*self.goroutines_tree.get_children())
        if self.session.machine is None:
            return
        for item in self.session.machine.snapshot()["goroutines"]:
            name = item["name"] or "(анонимная)"
            status = "остановлена" if item["killed"] else item["status"]
            self.goroutines_tree.insert(
                "",
                "end",
                values=(name, STATUS_LABELS.get(status, status), item["steps"]),
            )

    def _refresh_variables(self) -> None:
        self.variables_tree.delete(*self.variables_tree.get_children())
        if self.session.machine is None:
            return
        types = self.session.types
        for name, value in sorted(self.session.machine.variables.items()):
            self.variables_tree.insert(
                "", "end", iid=name, values=(name, types.get(name, ""), value)
            )

    def _update_status(self) -> None:
        machine = self.session.machine
        if machine is None:
            if self.session.compile_error:
                self.status_var.set("Ошибка компиляции")
            elif self.session.source:
                self.status_var.set("Не скомпилировано")
            else:
                self.status_var.set("Готово")
            return
        state = STATUS_LABELS.get(machine.status, machine.status)
        parts = [
            state,
            f"PC {machine.pc}/{len(machine.code)}",
            f"шагов {machine.steps}",
        ]
        if machine.last_instruction is not None:
            parts.append(format_instruction(machine.last_instruction))
        self.status_var.set("  |  ".join(parts))

    def _highlight_source_line(self, line: int | None) -> None:
        self.editor.tag_remove("current_line", "1.0", "end")
        if line is None or line < 1:
            return
        start = f"{line}.0"
        end = f"{line}.end"
        if self.editor.compare(start, "<", "end"):
            self.editor.tag_add("current_line", start, end)
            self.editor.see(start)

    def _highlight_error(self, line: int | None) -> None:
        self.editor.tag_remove("error_line", "1.0", "end")
        if line is None or line < 1:
            return
        start = f"{line}.0"
        end = f"{line}.end"
        if self.editor.compare(start, "<", "end"):
            self.editor.tag_add("error_line", start, end)

    def _clear_highlights(self) -> None:
        self.editor.tag_remove("current_line", "1.0", "end")
        self.editor.tag_remove("error_line", "1.0", "end")

    def _log(self, text: str, tag: str = "info") -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text.rstrip() + "\n", tag)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _flush_output(self) -> None:
        """Показать строки, напечатанные программой через print."""
        lines = self.session.output
        if len(lines) < self._shown_output:
            # машину перезапустили — вывод начинается заново
            self._shown_output = 0
        for line in lines[self._shown_output :]:
            self._log(line, "info")
        self._shown_output = len(lines)

    def _clear_output(self) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self._shown_output = 0

    # ------------------------------------------------------------------
    # файлы и примеры
    # ------------------------------------------------------------------

    def _sync_source(self) -> None:
        text = self.editor.get("1.0", "end-1c")
        mode = self._mode()
        if text != self.session.source or mode != self.session.mode:
            self.session.set_source(text, mode)

    def _mode(self) -> str:
        return MODE_LABELS.get(self.mode_var.get(), "program")

    def _on_mode_changed(self, _event=None) -> None:
        self._sync_source()
        self._log("Режим изменён, нужна повторная компиляция", "warn")
        self._refresh()

    def _on_source_modified(self, _event=None) -> None:
        if self._loading:
            return
        if not self.editor.edit_modified():
            return
        self._sync_source()
        self.editor.edit_modified(False)
        self._refresh()

    def _on_example_changed(self, _event=None) -> None:
        name = self.example_var.get()
        if name in EXAMPLES:
            self._load_example(name)

    def _load_example(self, name: str) -> None:
        self._stop_timer()
        self.mode_var.set("Программа")
        self._set_editor(EXAMPLES[name])
        self.example_var.set(name)
        self._path = None
        self._clear_output()
        self._log(f"Пример: {name}", "info")
        self._refresh()

    def _set_editor(self, text: str) -> None:
        self._loading = True
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self._loading = False
        self.session.set_source(text, self._mode())
        self._last_status = ""

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Открыть программу",
            filetypes=[("Stack Lang", "*.lang *.txt"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Ошибка", str(error))
            return
        self._path = Path(path)
        self._set_editor(text)
        self._clear_output()
        self._log(f"Открыт файл: {path}", "info")
        self._refresh()

    def save_file(self) -> None:
        path = self._path
        if path is None:
            chosen = filedialog.asksaveasfilename(
                title="Сохранить программу",
                defaultextension=".lang",
                filetypes=[("Stack Lang", "*.lang"), ("Все файлы", "*.*")],
            )
            if not chosen:
                return
            path = Path(chosen)
        try:
            path.write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Ошибка", str(error))
            return
        self._path = path
        self._log(f"Сохранено: {path}", "success")

    def _toggle_breakpoint(self, event) -> str | None:
        iid = self.code_tree.identify_row(event.y)
        if not iid:
            return None
        self.session.toggle_breakpoint(int(iid))
        self._refresh_code()
        return "break"

    def _on_code_select(self, _event=None) -> None:
        selection = self.code_tree.selection()
        if not selection:
            return
        pc = int(selection[0])
        lines = self.session.lines
        if 0 <= pc < len(lines):
            self._highlight_source_line(lines[pc])

    def _stop_timer(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    def close(self) -> None:
        self._stop_timer()
        self.root.destroy()


def main() -> None:
    enable_dpi_awareness()
    root = tk.Tk()
    apply_tk_scaling(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
