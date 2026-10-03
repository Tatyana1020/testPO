"""Синтаксическая проверка выражений по грамматике

    выражение := [+-] операнд { "!" } { бинарная операция ОПЕРАНД }
    операнд   := имя | константа | "(" выражение ")"

Байт-код не генерируется, дерево разбора не строится: рекурсивный спуск
только проверяет соответствие входной строки грамматике.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

BINARY_OPS = frozenset(
    {"+", "-", "*", "/", "%", "<", ">", "<=", ">=", "==", "!=", "&&", "||"}
)
PREFIX_OPS = frozenset({"+", "-"})
TWO_CHAR_OPS = frozenset({"<=", ">=", "==", "!=", "&&", "||"})


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    pos: int


class SyntaxErrorEx(Exception):
    def __init__(self, message: str, source: str, pos: int) -> None:
        line = source.count("\n", 0, pos) + 1
        col = pos - (source.rfind("\n", 0, pos))
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


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit():
            j = i
            while j < n and source[j].isdigit():
                j += 1
            tokens.append(Token("INT", source[i:j], i))
            i = j
        elif ch.isalpha() or ch == "_":
            j = i
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            tokens.append(Token("NAME", source[i:j], i))
            i = j
        elif ch == "(":
            tokens.append(Token("LPAREN", ch, i))
            i += 1
        elif ch == ")":
            tokens.append(Token("RPAREN", ch, i))
            i += 1
        elif source[i : i + 2] in TWO_CHAR_OPS:
            tokens.append(Token("OP", source[i : i + 2], i))
            i += 2
        elif ch in BINARY_OPS:
            tokens.append(Token("OP", ch, i))
            i += 1
        elif ch == "!":
            tokens.append(Token("FACTORIAL", ch, i))
            i += 1
        else:
            raise SyntaxErrorEx(f"Неизвестный символ {ch!r}", source, i)
    tokens.append(Token("EOF", "", n))
    return tokens


class Checker:
    def __init__(self, tokens: list[Token], source: str) -> None:
        self._tokens = tokens
        self._source = source
        self._i = 0

    @property
    def current(self) -> Token:
        return self._tokens[self._i]

    def _advance(self) -> Token:
        token = self._tokens[self._i]
        self._i += 1
        return token

    def _describe(self, token: Token) -> str:
        return "конец строки" if token.kind == "EOF" else repr(token.text)

    def _take(self, kind: str, text: str) -> Token:
        token = self.current
        if token.kind != kind or token.text != text:
            raise SyntaxErrorEx(
                f"Ожидалось {text!r}, получено {self._describe(token)}",
                self._source,
                token.pos,
            )
        return self._advance()

    def _at_op(self, ops: frozenset[str]) -> bool:
        token = self.current
        return token.kind == "OP" and token.text in ops

    def expression(self) -> None:
        if self._at_op(PREFIX_OPS):
            self._advance()
        self.operand()
        while self.current.kind == "FACTORIAL":
            self._advance()
        while self._at_op(BINARY_OPS):
            self._advance()
            self.operand()

    def operand(self) -> None:
        token = self.current
        if token.kind in ("NAME", "INT"):
            self._advance()
            return
        if token.kind == "LPAREN":
            self._advance()
            self.expression()
            self._take("RPAREN", ")")
            return
        raise SyntaxErrorEx(
            "Ожидался операнд: имя, константа или '(' выражение ')', "
            f"получено {self._describe(token)}",
            self._source,
            token.pos,
        )

    def finish(self) -> None:
        token = self.current
        if token.kind != "EOF":
            raise SyntaxErrorEx(
                f"Лишний токен {self._describe(token)} после выражения",
                self._source,
                token.pos,
            )


def check(source: str) -> None:
    checker = Checker(tokenize(source), source)
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