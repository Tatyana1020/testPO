"""GUI-слой проекта.

Пакет не содержит логики языка: компилятор и машина живут в
``stack_compiler``. Контроллер можно тестировать без Tkinter.
"""

from .controller import DebugSession

__all__ = ["DebugSession"]
