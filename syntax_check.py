"""Синтаксическая проверка выражений по грамматике

    выражение := { "+" | "-" | "!" } операнд { "!" } { бинарная операция ОПЕРАНД }
    операнд   := имя | константа | "(" выражение ")"

Разбор выполняется напрямую по символам исходного текста: отдельный
лексический этап отсутствует, дерево разбора и байт-код не строятся.
"""

from __future__ import annotations

import sys

BINARY_OPS = ("||", "&&", "<=", ">=", "==", "!=", "+", "-", "*", "/", "%", "<", ">")
PREFIX_OPS = ("+", "-", "!")


class SyntaxErrorEx(Exception):
    def __init__(self, message: str, source: str, pos: int) -> None:
        line = source.count("\n", 0, pos) + 1
        col = pos - source.rfind("\n", 0, pos)
        lines = source.splitlines()
        excerpt = lines[line - 1] if lines else ""
        super().__init__(
            f"{message}\n"
            f"  позиция: строка {line}, столбец {col}\n"
            f"  {excerpt}\n"
            f"  {' ' * (col - 1)}^"
        )
        self.message = message
        self.line = line
        self.column = col


class Checker:
    def __init__(self, source: str) -> None:
        self._source = source
        self._i = 0

    def _peek(self, offset: int = 0) -> str:
        j = self._i + offset
        return self._source[j] if 0 <= j < len(self._source) else ""

    def _skip_spaces(self) -> None:
        while self._peek() and self._peek().isspace():
            self._i += 1

    def _at_end(self) -> bool:
        self._skip_spaces()
        return self._i >= len(self._source)

    def _here(self) -> str:
        return "конец строки" if self._at_end() else repr(self._peek())

    def _error(self, message: str) -> SyntaxErrorEx:
        self._skip_spaces()
        return SyntaxErrorEx(
            message, self._source, min(self._i, len(self._source))
        )

    def _eat(self, char: str, expected: str) -> None:
        self._skip_spaces()
        if self._peek() != char:
            raise self._error(f"Ожидалось {expected}, получено {self._here()}")
        self._i += 1

    def _match_op(self, operators: tuple[str, ...]) -> str:
        self._skip_spaces()
        for op in operators:
            if self._source.startswith(op, self._i):
                self._i += len(op)
                return op
        return ""

    def _match_prefix(self) -> bool:
        self._skip_spaces()
        matched = False
        while self._peek() in PREFIX_OPS:
            self._i += 1
            matched = True
            self._skip_spaces()
        return matched

    def _starts_inequality(self) -> bool:
        return self._source.startswith("!=", self._i) and not (
            self._source.startswith("!==", self._i)
        )

    def _match_factorials(self) -> None:
        self._skip_spaces()
        while self._peek() == "!" and not self._starts_inequality():
            self._i += 1
            self._skip_spaces()

    def expression(self) -> None:
        self._match_prefix()
        self.operand()
        self._match_factorials()
        while self._match_op(BINARY_OPS):
            self.operand()

    def operand(self) -> None:
        self._skip_spaces()
        char = self._peek()
        if char.isalpha() or char == "_":
            self._i += 1
            while self._peek().isalnum() or self._peek() == "_":
                self._i += 1
            return
        if char.isdigit():
            while self._peek().isdigit():
                self._i += 1
            return
        if char == "(":
            self._i += 1
            self.expression()
            self._eat(")", "')'")
            return
        raise self._error(
            "Ожидался операнд: имя, константа или '(' выражение ')'. "
            f"Получено {self._here()}"
        )

    def finish(self) -> None:
        if not self._at_end():
            raise self._error(
                f"Лишний символ {self._peek()!r} после выражения"
            )


def check(source: str) -> None:
    checker = Checker(source)
    checker.expression()
    checker.finish()


def main(argv: list[str]) -> int:
    source = argv[1] if len(argv) > 1 else sys.stdin.read()
    try:
        check(source)
    except SyntaxErrorEx as error:
        print(f"Ошибка: {error.message}")
        print(error)
        return 1
    print("Синтаксис корректен.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))