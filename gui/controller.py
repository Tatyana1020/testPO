from __future__ import annotations

from stack_compiler import CompileError, Machine, compile_expression, compile_program


def format_instruction(instruction: tuple) -> str:
    op, *args = instruction
    return " ".join(str(part) for part in (op, *args))


class DebugSession:
    """Состояние одного запуска: исходник, байт-код, машина и брейкпоинты.

    Здесь нет Tkinter и вообще никакого UI. GUI только читает снимки
    состояния и вызывает методы ``compile``, ``step``, ``reset``.
    """

    def __init__(self) -> None:
        self.source = ""
        self.mode = "program"
        self.code = None
        self.machine: Machine | None = None
        self.breakpoints: set[int] = set()
        self.compile_error: CompileError | None = None
        self.trace: list[str] = []
        self.dirty = True
        self._skip_breakpoint: int | None = None

    @property
    def lines(self) -> list[int]:
        if self.code is None:
            return []
        return list(getattr(self.code, "lines", [1] * len(self.code)))

    @property
    def output(self) -> list[str]:
        """Строки, напечатанные программой через ``print``."""
        if self.machine is None:
            return []
        return list(self.machine.output)

    @property
    def types(self) -> dict[str, str]:
        """Объявленные типы переменных: имя -> «int» или «int[]»."""
        if self.code is None:
            return {}
        return dict(getattr(self.code, "types", {}))

    @property
    def status(self) -> str:
        if self.compile_error is not None:
            return "error"
        if self.machine is None:
            return "empty"
        return self.machine.status

    @property
    def error(self) -> str | None:
        if self.compile_error is not None:
            return str(self.compile_error)
        if self.machine is not None and self.machine.error is not None:
            return str(self.machine.error)
        return None

    @property
    def error_line(self) -> int | None:
        if self.compile_error is not None:
            return self.compile_error.line
        if self.machine is not None and self.machine.error is not None:
            pc = self.machine.pc
            if 0 <= pc < len(self.lines):
                return self.lines[pc]
        return None

    def set_source(self, source: str, mode: str | None = None) -> None:
        self.source = source
        if mode is not None:
            self.mode = mode
        self.code = None
        self.machine = None
        self.breakpoints.clear()
        self.trace.clear()
        self.dirty = True
        self.compile_error = None

    def compile(self, source: str | None = None, mode: str | None = None) -> bool:
        if source is not None:
            self.source = source
        if mode is not None:
            self.mode = mode
        self.compile_error = None
        self.trace.clear()
        self._skip_breakpoint = None
        try:
            if self.mode == "expression":
                code = compile_expression(self.source)
            else:
                code = compile_program(self.source)
        except CompileError as error:
            self.code = None
            self.machine = None
            self.compile_error = error
            self.dirty = False
            return False

        self.code = code
        self.machine = Machine(code)
        self.dirty = False
        return True

    def ensure_compiled(self) -> bool:
        if self.dirty or self.machine is None:
            return self.compile()
        return self.compile_error is None and self.machine is not None

    def step(self) -> bool:
        if not self.ensure_compiled() or self.machine is None:
            return False
        pc = self.machine.pc
        instruction = (
            self.code[pc] if self.code is not None and 0 <= pc < len(self.code) else None
        )
        ok = self.machine.step()
        if instruction is not None:
            self.trace.append(f"{pc:04d}  {format_instruction(instruction)}")
            del self.trace[:-200]
        self._skip_breakpoint = None
        return ok

    def reset(self) -> None:
        self.trace.clear()
        self._skip_breakpoint = None
        if self.machine is not None:
            self.machine.reset()

    def toggle_breakpoint(self, pc: int) -> bool:
        if pc in self.breakpoints:
            self.breakpoints.remove(pc)
            return False
        self.breakpoints.add(pc)
        return True

    def at_breakpoint(self) -> bool:
        return (
            self.machine is not None
            and self.machine.status in ("ready", "paused")
            and self.machine.pc in self.breakpoints
            and self.machine.pc != self._skip_breakpoint
        )

    def resume(self) -> None:
        """Не останавливаться сразу на текущей точке останова."""
        if self.machine is not None and self.machine.pc in self.breakpoints:
            self._skip_breakpoint = self.machine.pc
        else:
            self._skip_breakpoint = None

    def current_line(self) -> int | None:
        if self.machine is None:
            return None
        pc = self.machine.pc
        if 0 <= pc < len(self.lines):
            return self.lines[pc]
        return None

    def snapshot(self) -> dict:
        if self.machine is None:
            return {
                "pc": 0,
                "code_len": len(self.code) if self.code is not None else 0,
                "stack": [],
                "variables": {},
                "steps": 0,
                "status": self.status,
                "error": self.error,
                "result": None,
                "line": self.error_line,
                "lines": self.lines,
                "types": self.types,
                "code": self.code or [],
            }
        view = self.machine.snapshot()
        view["line"] = self.current_line()
        view["lines"] = self.lines
        view["types"] = self.types
        view["code"] = self.code or []
        return view

    def run_all(self) -> int | None:
        """Выполнить всё до конца (удобно для тестов и CLI-подобных сценариев)."""
        if not self.ensure_compiled() or self.machine is None:
            return None
        while self.step():
            pass
        return self.machine.result
