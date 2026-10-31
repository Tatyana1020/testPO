"""Однопроходный компилятор выражений и операторов в код стековой машины.

Грамматика (приоритет операций от низшего к высшему):

    программа  := { оператор }
    оператор   := объявление
                | "if" выр блок { "else" "if" выр блок } [ "else" блок ]
                | "while" выр блок
                | блок
                | имя "=" выр ";"
                | имя "[" выр "]" "=" выр ";"
                | выр ";"
    блок       := "{" { оператор } "}"
    объявление := "int" имя [ "[" выр "]" ] [ "=" инициализатор ] ";"
    инициализатор := "[" { выр { "," выр } } "]" | выр
    выр        := сравнение { ("&&" | "||") сравнение }
    сравнение  := сумма { ("<" | ">" | "==" | "!=" | "<>" | "<=" | ">=") сумма }
    сумма      := слаг { ("+" | "-") слаг }
    слаг       := множ { ("*" | "/" | "%") множ }
    множ       := операнд [ "^" операнд ]
    операнд    := имя | конст | "(" выр ")" | вызов { постфикс }
    постфикс   := "!" | "[" выр "]"
    вызов      := имя "(" [ выр { "," выр } ] ")"

Разбор идёт напрямую по символам исходного текста (лексера нет), дерево
разбора не строится: код стековой машины выпускается по мере разбора,
переходы если/пока дописываются на месте (патчинг адресов).

Типы: в языке их два — ``int`` и ``int[]``. Переменная обязана быть
объявлена (``int x;``) до первого использования; проверка типов выполняется
на этапе компиляции, см. модуль ``stack_types``.
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Iterable

from stack_types import (
    TYPE_KEYWORD_NAMES,
    TYPE_KEYWORDS,
    SymbolTable,
    Type,
    array_of,
    assignable,
    convert_kind,
    promote,
)

LOGICAL_OPS = ("&&", "||")
COMPARISON_OPS = ("<>", "!=", "<=", ">=", "==", "<", ">")
SUM_OPS = ("+", "-")
TERM_OPS = ("*", "/", "%")
POWER_OPS = ("^",)
PREFIX_OPS = ("+", "-", "!")
KEYWORDS = (*TYPE_KEYWORD_NAMES, "if", "else", "while")

#: Функции-преобразования: имя -> тип результата.
CONVERT_FUNCTIONS = {
    "int": Type.INT,
    "float": Type.FLOAT,
    "double": Type.DOUBLE,
    "string": Type.STRING,
}

#: Значение, которым заполняется новый массив, по типу элемента.
ARRAY_FILL = {
    "int": 0,
    "float": 0.0,
    "double": 0.0,
    "string": "",
}

#: Управляющие последовательности в строковых литералах.
STRING_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    "\\": "\\",
    '"': '"',
    "'": "'",
}

OPCODES = {
    "&&": "AND",
    "||": "OR",
    "<": "LT",
    ">": "GT",
    "==": "EQ",
    "!=": "NE",
    "<>": "NE",
    "<=": "LE",
    ">=": "GE",
}

#: Опкоды сравнений (применимы и к числам, и к строкам).
COMPARISON_OPCODES = ("LT", "GT", "EQ", "NE", "LE", "GE")

BINARY_OPS = {
    "ADD": lambda a, b: a + b,
    "SUB": lambda a, b: a - b,
    "MUL": lambda a, b: a * b,
    "DIV": lambda a, b: _div(a, b),
    "MOD": lambda a, b: a % b,
    "POW": lambda a, b: a**b,
    "AND": lambda a, b: 1 if a and b else 0,
    "OR": lambda a, b: 1 if a or b else 0,
    "LT": lambda a, b: int(a < b),
    "GT": lambda a, b: int(a > b),
    "EQ": lambda a, b: int(a == b),
    "NE": lambda a, b: int(a != b),
    "LE": lambda a, b: int(a <= b),
    "GE": lambda a, b: int(a >= b),
}


class CompileRuntimeError(Exception):
    pass


class Array:
    def __init__(self, items: list | None = None, size: int = 0) -> None:
        self.items = [0] * size if items is None else list(items)

    def __len__(self) -> int:
        return len(self.items)

    def __repr__(self) -> str:
        parts = [
            repr(item) if isinstance(item, str) else str(item)
            for item in self.items
        ]
        return "[" + ", ".join(parts) + "]"


def _resize(array, size):
    if not isinstance(array, Array):
        raise CompileRuntimeError("resize: ожидался массив")
    if size < 0:
        raise CompileRuntimeError("resize: отрицательный размер")
    delta = size - len(array.items)
    if delta > 0:
        array.items.extend([0] * delta)
    else:
        del array.items[size:]
    return 0


def _to_int(value):
    """Явное преобразование в целое число."""
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            raise CompileRuntimeError(
                f"Не удалось преобразовать строку '{value}' в целое число"
            ) from None
    if isinstance(value, float):
        return int(value)
    if isinstance(value, int):
        return value
    raise CompileRuntimeError("Преобразование в целое не поддерживается")


def _to_float(value):
    """Явное преобразование в вещественное число."""
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            raise CompileRuntimeError(
                f"Не удалось преобразовать строку '{value}' в число"
            ) from None
    if isinstance(value, (int, float)):
        return float(value)
    raise CompileRuntimeError("Преобразование в вещественное не поддерживается")


def _to_string(value):
    """Явное преобразование в строку."""
    if isinstance(value, str):
        return value
    if isinstance(value, Array):
        return repr(value)
    return str(value)


#: Преобразования, доступные инструкции CONVERT.
CONVERTERS = {
    "int": _to_int,
    "float": _to_float,
    "double": _to_float,
    "string": _to_string,
}


BUILTIN_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "resize": _resize,
}

DEFAULT_MAX_STEPS = 1_000_000


def _plural_args(count: int) -> str:
    """Согласовать слово «аргумент» с числом."""
    if count % 10 == 1 and count % 100 != 11:
        return "аргумент"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "аргумента"
    return "аргументов"


class CompileError(Exception):
    def __init__(self, message: str, source: str, pos: int) -> None:
        line = source.count("\n", 0, pos) + 1
        col = pos - source.rfind("\n", 0, pos)
        lines = source.split("\n")
        excerpt = lines[line - 1] if 0 <= line - 1 < len(lines) else ""
        super().__init__(
            f"{message}\n"
            f"  позиция: строка {line}, столбец {col}\n"
            f"  {excerpt}\n"
            f"  {' ' * (col - 1)}^"
        )
        self.message = message
        self.line = line
        self.column = col


class CodeBuffer(list):
    """Список инструкций с параллельной картой строк исходника."""

    def __init__(self, source: str, position) -> None:
        super().__init__()
        self._source = source
        self._position = position
        self.lines: list[int] = []
        self.types: dict[str, str] = {}

    def append(self, instruction: tuple) -> None:
        pos = self._position()
        self.lines.append(self._source.count("\n", 0, pos) + 1)
        super().append(instruction)

    def truncate(self, size: int) -> None:
        del self[size:]
        del self.lines[size:]


class Compiler:
    def __init__(
        self,
        source: str,
        declared: Iterable[str | tuple[str, Type]] = (),
    ) -> None:
        self._source = source
        self._i = 0
        self.code = CodeBuffer(source, lambda: self._i)
        self.symbols = SymbolTable(declared)
        self._loop_depth = 0

    def _peek(self, offset: int = 0) -> str:
        j = self._i + offset
        return self._source[j] if 0 <= j < len(self._source) else ""

    def _skip(self) -> None:
        while self._peek() and self._peek().isspace():
            self._i += 1

    def _at_end(self) -> bool:
        self._skip()
        return self._i >= len(self._source)

    def _here(self) -> str:
        return "конец строки" if self._at_end() else repr(self._peek())

    def _error(self, message: str) -> CompileError:
        self._skip()
        return CompileError(message, self._source, min(self._i, len(self._source)))

    def _take_char(self, char: str, expected: str) -> None:
        self._skip()
        if self._peek() != char:
            raise self._error(f"Ожидалось {expected}, получено {self._here()}")
        self._i += 1

    def _match_op(self, operators: tuple[str, ...]) -> str:
        self._skip()
        for op in operators:
            if self._source.startswith(op, self._i):
                self._i += len(op)
                return op
        return ""

    def _match_kw(self, word: str) -> bool:
        self._skip()
        if not self._source.startswith(word, self._i):
            return False
        nxt = self._source[self._i + len(word) : self._i + len(word) + 1]
        if nxt and (nxt.isalnum() or nxt == "_"):
            return False
        self._i += len(word)
        return True

    def _match_type_keyword(self) -> str | None:
        """Распознать ключевое слово типа в начале оператора.

        ``int(3)`` — это вызов преобразования, а не объявление, поэтому
        такой случай откатывается.
        """
        for name in TYPE_KEYWORD_NAMES:
            if not self._match_kw(name):
                continue
            self._skip()
            if self._peek() == "(":
                self._i -= len(name)
                return None
            return name
        return None

    def _starts_inequality(self) -> bool:
        return self._source.startswith("!=", self._i) and not (
            self._source.startswith("!==", self._i)
        )

    def _emit_jump(self, op: str) -> int:
        self.code.append((op, -1))
        return len(self.code) - 1

    def _patch(self, index: int, target: int) -> None:
        self.code[index] = (self.code[index][0], target)

    # -- проверки типов ---------------------------------------------------

    def _error_at(self, message: str, pos: int) -> CompileError:
        """Ошибка компиляции с указанием конкретной позиции в исходнике."""
        return CompileError(message, self._source, min(pos, len(self._source)))

    def _fail_type(self, message: str, pos: int | None = None) -> None:
        """Поднять ошибку типа: в позиции ``pos`` либо в текущей."""
        if pos is None:
            raise self._error(message)
        raise self._error_at(message, pos)

    def _symbol_type(self, name: str, pos: int) -> Type:
        """Тип объявленной переменной; ошибка, если переменной нет."""
        symbol = self.symbols.lookup(name)
        if symbol is None:
            self._fail_type(f"Переменная '{name}' не объявлена", pos)
        return symbol.type

    def _check_assignment(self, name: str, value_type: Type, pos: int) -> None:
        """Проверить, что присваиваемое значение совместимо с типом цели."""
        symbol = self.symbols.lookup(name)
        if symbol is None:
            self._fail_type(f"Переменная '{name}' не объявлена", pos)
        if not assignable(symbol.type, value_type):
            self._fail_type(
                f"Нельзя присвоить значение типа {value_type} "
                f"переменной '{name}' типа {symbol.type}",
                pos,
            )
        self._emit_convert(symbol.type, value_type)

    def _check_call(self, name: str, arg_types: list[Type]) -> Type:
        """Проверить вызов встроенной функции и вернуть тип результата.

        Неизвестные функции разрешены: их могут подставить при запуске
        (``Machine(code, functions=...)``), поэтому аргументы не проверяются,
        а результат считается ``int``.
        """
        if name == "abs":
            self._check_arity(name, arg_types, 1)
            self._require_numeric(name, arg_types[0], 1)
            return arg_types[0]
        if name == "sqrt":
            self._check_arity(name, arg_types, 1)
            self._require_numeric(name, arg_types[0], 1)
            return Type.FLOAT
        if name in ("min", "max"):
            if len(arg_types) < 1:
                self._fail_type(
                    f"Функция '{name}' ожидает не менее 1 аргумента, "
                    f"получено 0"
                )
            for index, arg_type in enumerate(arg_types):
                self._require_numeric(name, arg_type, index + 1)
            result = arg_types[0]
            for arg_type in arg_types[1:]:
                result = promote(result, arg_type)
            return result
        if name == "resize":
            self._check_arity(name, arg_types, 2)
            if not arg_types[0].is_array:
                self._fail_type(
                    f"Аргумент 1 функции '{name}' должен иметь тип массива, "
                    f"получено {arg_types[0]}"
                )
            self._require_numeric(name, arg_types[1], 2)
            return Type.INT
        # Неизвестная функция: подставляется при запуске.
        return Type.INT

    def _check_arity(self, name: str, arg_types: list[Type], arity: int) -> None:
        if len(arg_types) != arity:
            self._fail_type(
                f"Функция '{name}' ожидает {arity} "
                f"{_plural_args(arity)}, получено {len(arg_types)}"
            )

    def _require_numeric(self, name: str, arg_type: Type, index: int) -> None:
        if not arg_type.is_numeric:
            self._fail_type(
                f"Аргумент {index} функции '{name}' должен иметь числовой тип, "
                f"получено {arg_type}"
            )

    def _require_operands(self, left: Type, right: Type, op: str) -> None:
        """Операнды должны быть числами (строки допустимы только для ``+``)."""
        for type_ in (left, right):
            if type_.is_array:
                self._fail_type(f"Операция '{op}' не применима к массиву")
            if type_ is Type.STRING:
                self._fail_type(f"Операция '{op}' не применима к строке")

    def _arith_type(self, left: Type, right: Type, op: str) -> Type:
        """Тип результата арифметической операции."""
        if op == "+" and left is Type.STRING and right is Type.STRING:
            return Type.STRING
        self._require_operands(left, right, op)
        if op == "%":
            if left is not Type.INT or right is not Type.INT:
                self._fail_type("Операция '%' применима только к целым числам")
            return Type.INT
        return promote(left, right)

    def _compare_type(self, left: Type, right: Type, op: str) -> Type:
        """Тип результата сравнения: всегда ``int`` (0 или 1).

        Сравнивать можно числа между собой и строки между собой.
        """
        if left is Type.STRING and right is Type.STRING:
            return Type.INT
        self._require_operands(left, right, op)
        return Type.INT

    def _check_convert(self, name: str, arg_types: list[Type]) -> None:
        """Проверить вызов функции-преобразования."""
        self._check_arity(name, arg_types, 1)
        source = arg_types[0]
        if not source.is_numeric and source is not Type.STRING:
            self._fail_type(
                f"Аргумент 1 функции '{name}' должен иметь числовой или "
                f"строковый тип, получено {source}"
            )

    def _check_print(self, arg_types: list[Type]) -> None:
        """``print`` принимает любые типы и любое число аргументов."""
        return

    def program(self) -> list[tuple]:
        while not self._at_end():
            self.statement()
        self._publish_types()
        return self.code

    def _publish_types(self) -> None:
        """Передать объявленные типы в буфер кода — их показывает GUI."""
        self.code.types = {
            name: str(type_) for name, type_ in self.symbols.as_types().items()
        }

    def statement(self) -> None:
        self._skip()
        if self._match_kw("if"):
            self.if_statement()
            return
        if self._match_kw("while"):
            self.while_statement()
            return
        type_keyword = self._match_type_keyword()
        if type_keyword is not None:
            self.declaration(type_keyword)
            return
        if self._peek() == "{":
            self.block()
            return
        if self._peek() == ";":
            self._i += 1
            return
        if self._try_element_assignment():
            self._skip()
            if not self._at_end():
                self._take_char(";", "';'")
            return
        name_pos = self._i
        name = self._try_assignment()
        pending: tuple[str, Type, int] | None = None
        if name is not None:
            value_type = self.expression()
            pending = (name, value_type, name_pos)
        else:
            self.expression()
            self.code.append(("POP",))
        self._skip()
        if not self._at_end():
            self._take_char(";", "';'")
        # Тип присваивания проверяем после того, как оператор разобран целиком:
        # синтаксическая ошибка в «;» важнее ошибки типа. STORE выпускается
        # здесь же: между выражением и ним ничего не эмитится.
        if pending is not None:
            self._check_assignment(*pending)
            self.code.append(("STORE", name))

    def declaration(self, type_keyword: str) -> None:
        base_type = TYPE_KEYWORDS[type_keyword]
        self._skip()
        name = self._ident()
        name_pos = self._i - len(name)
        self._skip()
        if self._loop_depth > 0:
            self._fail_type(
                "Объявление переменной внутри тела цикла запрещено", name_pos
            )
        if name in self.symbols:
            self._fail_type(f"Переменная '{name}' уже объявлена", name_pos)
        has_size = False
        type_ = base_type
        if self._peek() == "[":
            if self._size_followed_by_literal():
                raise self._error(
                    "Массив не может иметь одновременно размер и список "
                    "инициализации"
                )
            self._i += 1
            size_pos = self._i
            size_type = self.expression()
            if size_type is not Type.INT:
                self._fail_type(
                    f"Размер массива должен иметь тип int, получено {size_type}",
                    size_pos,
                )
            self._take_char("]", "']'")
            self.code.append(("NEWARR", base_type.value))
            has_size = True
            type_ = array_of(base_type)
            self._skip()
        if self._peek() == "=" and not self._source.startswith("==", self._i):
            self._i += 1
            self._skip()
            if self._peek() == "[":
                self.array_literal(base_type)
                type_ = array_of(base_type)
            else:
                init_pos = self._i
                init_type = self.expression()
                self._check_assignable(
                    f"Инициализатор переменной '{name}' должен иметь тип",
                    base_type,
                    init_type,
                    init_pos,
                )
                self._emit_convert(base_type, init_type)
        elif not has_size:
            self.code.append(("PUSH", ARRAY_FILL[base_type.value]))
        self.code.append(("DECL", name))
        self.symbols.declare(name, type_, name_pos)
        self._take_char(";", "';'")

    def _check_assignable(
        self, prefix: str, target: Type, source: Type, pos: int
    ) -> None:
        """Проверить, что значение типа ``source`` годится для ``target``.

        ``prefix`` — начало сообщения вплоть до слова «тип», например
        «Элемент массива должен иметь тип».
        """
        if not assignable(target, source):
            self._fail_type(
                f"{prefix} {target}, получено {source}", pos
            )

    def _emit_convert(self, target: Type, source: Type) -> None:
        """Выпустить преобразование значения, если типы различаются."""
        if target is source:
            return
        kind = convert_kind(target)
        if kind is not None:
            self.code.append(("CONVERT", kind))

    def array_literal(self, element_type: Type) -> Type:
        """Разобрать список инициализации массива.

        Элементы должны иметь тип ``element_type`` (или сужаться к нему
        неявно нельзя — только расширяться).
        """
        self._take_char("[", "'['")
        count = 0
        self._skip()
        if self._peek() != "]":
            count = self._array_element(element_type)
            while self._match_op((",",)):
                count += self._array_element(element_type)
        self._take_char("]", "']'")
        self.code.append(("MKARR", count))
        return array_of(element_type)

    def _array_element(self, element_type: Type) -> int:
        """Разобрать один элемент списка инициализации."""
        element_pos = self._i
        value_type = self.expression()
        self._check_assignable(
            "Элемент массива должен иметь тип",
            element_type,
            value_type,
            element_pos,
        )
        self._emit_convert(element_type, value_type)
        return 1

    def _size_followed_by_literal(self) -> bool:
        depth = 0
        j = self._i
        while j < len(self._source):
            char = self._source[j]
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(self._source):
            return False
        k = j + 1
        while k < len(self._source) and self._source[k].isspace():
            k += 1
        return self._source[k : k + 1] == "=" and self._source[k + 1 :].lstrip()[:1] == "["

    def _try_element_assignment(self) -> bool:
        """Разобрать ``имя[индекс] = значение;``.

        Разбор спекулятивный: если ``=`` не найдено, откатываем и курсор,
        и буфер кода. Поэтому проверки типов, зависящие от того, присваивание
        это или чтение, делаем только после того, как ``=`` подтверждён.
        """
        start = self._i
        mark = len(self.code)
        if not (self._peek().isalpha() or self._peek() == "_"):
            return False
        name = self._ident()
        name_pos = start
        self.code.append(("LOAD", name))
        self._skip()
        if self._peek() != "[":
            self._i = start
            self.code.truncate(mark)
            return False
        bracket_pos = self._i
        self._i += 1
        index_pos = self._i
        index_type = self.expression()
        if index_type is not Type.INT:
            self._fail_type(
                f"Индекс массива должен иметь тип int, получено {index_type}",
                index_pos,
            )
        self._take_char("]", "']'")
        self._skip()
        if self._peek() == "=" and not self._source.startswith("==", self._i):
            self._i += 1
            # Дальше это точно запись в элемент — типы проверять можно.
            symbol = self.symbols.lookup(name)
            if symbol is None:
                self._fail_type(f"Переменная '{name}' не объявлена", name_pos)
            if not symbol.type.is_array:
                self._fail_type(
                    "Индексация возможна только для массива", bracket_pos
                )
            value_pos = self._i
            value_type = self.expression()
            element_type = symbol.type.element
            self._check_assignable(
                "Значение элемента массива должно иметь тип",
                element_type,
                value_type,
                value_pos,
            )
            self._emit_convert(element_type, value_type)
            self.code.append(("SETIDX",))
            return True
        self._i = start
        self.code.truncate(mark)
        return False

    def if_statement(self) -> None:
        jumps: list[int] = []
        while True:
            condition_pos = self._i
            condition_type = self.expression()
            if condition_type is not Type.INT:
                self._fail_type(
                    f"Условие должно иметь тип int, получено {condition_type}",
                    condition_pos,
                )
            jz = self._emit_jump("JZ")
            self.block()
            jumps.append(self._emit_jump("JMP"))
            self._patch(jz, len(self.code))
            if not self._match_kw("else"):
                break
            if self._match_kw("if"):
                continue
            self.block()
            break
        end = len(self.code)
        for index in jumps:
            self._patch(index, end)

    def while_statement(self) -> None:
        start = len(self.code)
        condition_pos = self._i
        condition_type = self.expression()
        if condition_type is not Type.INT:
            self._fail_type(
                f"Условие должно иметь тип int, получено {condition_type}",
                condition_pos,
            )
        jz = self._emit_jump("JZ")
        # Внутри цикла объявлять переменные нельзя: без областей видимости
        # инструкция DECL выполнилась бы на каждой итерации.
        self._loop_depth += 1
        try:
            self.block()
        finally:
            self._loop_depth -= 1
        self.code.append(("JMP", start))
        self._patch(jz, len(self.code))

    def block(self) -> None:
        self._take_char("{", "'{'")
        while True:
            self._skip()
            if self._peek() == "}":
                self._i += 1
                return
            if self._at_end():
                raise self._error(f"Ожидалось '}}', получено {self._here()}")
            self.statement()

    def _try_assignment(self) -> str | None:
        start = self._i
        if not (self._peek().isalpha() or self._peek() == "_"):
            return None
        while self._peek().isalnum() or self._peek() == "_":
            self._i += 1
        name = self._source[start : self._i]
        self._skip()
        if self._peek() == "=" and not self._source.startswith("==", self._i):
            self._i += 1
            return name
        self._i = start
        return None

    def expression(self) -> Type:
        left = self.comparison()
        while True:
            op = self._match_op(LOGICAL_OPS)
            if not op:
                break
            self._check_operand(left, op)
            right = self.comparison()
            self._require_operands(left, right, op)
            self.code.append((OPCODES[op],))
            left = Type.INT
        return left

    def comparison(self) -> Type:
        left = self.sum()
        while True:
            op = self._match_op(COMPARISON_OPS)
            if not op:
                break
            self._check_operand(left, op)
            right = self.sum()
            self._compare_type(left, right, op)
            self.code.append((OPCODES[op],))
            left = Type.INT
        return left

    def sum(self) -> Type:
        left = self.term()
        while True:
            op = self._match_op(SUM_OPS)
            if not op:
                break
            self._check_operand(left, op)
            right = self.term()
            result_type = self._arith_type(left, right, op)
            self.code.append(("ADD" if op == "+" else "SUB",))
            left = result_type
        return left

    def term(self) -> Type:
        left = self.power()
        while True:
            op = self._match_op(TERM_OPS)
            if not op:
                break
            self._check_operand(left, op)
            right = self.power()
            result_type = self._arith_type(left, right, op)
            self.code.append(
                ("MUL" if op == "*" else "DIV" if op == "/" else "MOD",)
            )
            left = result_type
        return left

    def power(self) -> Type:
        left = self.operand()
        if self._match_op(POWER_OPS):
            self._check_operand(left, "^")
            right = self.operand()
            result_type = self._arith_type(left, right, "^")
            self.code.append(("POW",))
            return result_type
        return left

    def operand(self) -> Type:
        prefixes = self._collect_prefix()
        self._skip()
        char = self._peek()
        if char.isalpha() or char == "_":
            name = self._ident()
            name_pos = self._i - len(name)
            self._skip()
            if self._peek() == "(":
                type_ = self.call(name)
            else:
                type_ = self._symbol_type(name, name_pos)
                self.code.append(("LOAD", name))
        elif char.isdigit():
            literal_type, value = self._number()
            self.code.append(("PUSH", value))
            type_ = literal_type
        elif char in ("\"", "'"):
            self.code.append(("PUSH", self._string_literal()))
            type_ = Type.STRING
        elif char == "(":
            self._i += 1
            type_ = self.expression()
            self._take_char(")", "')'")
        else:
            raise self._error(
                "Ожидался операнд: имя, конст, строка, '(' выр ')' "
                "или вызов функции. "
                f"Получено {self._here()}"
            )
        type_ = self.postfix(type_)
        for sign in reversed(prefixes):
            if type_.is_array:
                self._fail_type(
                    f"Унарная операция '{sign}' не применима к массиву"
                )
            if type_ is Type.STRING:
                self._fail_type(
                    f"Унарная операция '{sign}' не применима к строке"
                )
            if sign == "-":
                self.code.append(("NEG",))
            elif sign == "!":
                self.code.append(("NOT",))
                type_ = Type.INT
        return type_

    def call(self, name: str) -> Type:
        self._take_char("(", "'('")
        arg_types: list[Type] = []
        self._skip()
        if self._peek() != ")":
            arg_types.append(self.expression())
            while self._match_op((",",)):
                arg_types.append(self.expression())
        self._take_char(")", "')'")
        if name == "print":
            self._check_print(arg_types)
            self.code.append(("PRINT", len(arg_types)))
            return Type.INT
        if name in CONVERT_FUNCTIONS:
            self._check_convert(name, arg_types)
            self.code.append(("CONVERT", name))
            return CONVERT_FUNCTIONS[name]
        result_type = self._check_call(name, arg_types)
        self.code.append(("CALL", name, len(arg_types)))
        return result_type

    def postfix(self, base: Type) -> Type:
        while True:
            self._skip()
            char = self._peek()
            if char == "[":
                if not base.is_array:
                    self._fail_type("Индексация возможна только для массива")
                self._i += 1
                index_pos = self._i
                index_type = self.expression()
                if index_type is not Type.INT:
                    self._fail_type(
                        f"Индекс массива должен иметь тип int, "
                        f"получено {index_type}",
                        index_pos,
                    )
                self._take_char("]", "']'")
                self.code.append(("INDEX",))
                base = base.element
            elif char == "!" and not self._starts_inequality():
                self._i += 1
                if base is not Type.INT:
                    self._fail_type("Факториал применим только к целым числам")
                self.code.append(("FACT",))
                base = Type.INT
            else:
                return base

    def _check_operand(self, type_: Type, op: str) -> None:
        """Операнд должен быть допустим для операции.

        Строки допустимы только в конкатенации и в сравнениях.
        """
        if type_.is_array:
            self._fail_type(f"Операция '{op}' не применима к массиву")
        if type_ is Type.STRING and not (
            op == "+" or op in COMPARISON_OPS
        ):
            self._fail_type(f"Операция '{op}' не применима к строке")

    def _collect_prefix(self) -> list[str]:
        self._skip()
        prefixes = []
        while self._peek() in PREFIX_OPS:
            if self._peek() == "!" and self._starts_inequality():
                break
            prefixes.append(self._peek())
            self._i += 1
            self._skip()
        return prefixes

    def _ident(self) -> str:
        start = self._i
        self._i += 1
        while self._peek().isalnum() or self._peek() == "_":
            self._i += 1
        return self._source[start : self._i]

    def _number(self) -> tuple[Type, int | float]:
        """Разобрать числовой литерал.

        ``42`` -> int, ``1.5`` -> double, ``1.5f`` -> float, ``1.5d`` -> double.
        Дробная часть и экспонента делают литерал вещественным.
        """
        start = self._i
        while self._peek().isdigit():
            self._i += 1
        is_float = False
        if self._peek() == "." and self._peek(1).isdigit():
            is_float = True
            self._i += 1
            while self._peek().isdigit():
                self._i += 1
        if self._peek() in ("e", "E") and (
            self._peek(1).isdigit()
            or (self._peek(1) in ("+", "-") and self._peek(2).isdigit())
        ):
            is_float = True
            self._i += 1
            if self._peek() in ("+", "-"):
                self._i += 1
            while self._peek().isdigit():
                self._i += 1
        text = self._source[start : self._i]
        if not is_float:
            return Type.INT, int(text)
        suffix = self._peek()
        if suffix in ("f", "F"):
            self._i += 1
            return Type.FLOAT, float(text)
        if suffix in ("d", "D"):
            self._i += 1
            return Type.DOUBLE, float(text)
        return Type.DOUBLE, float(text)

    def _string_literal(self) -> str:
        """Разобрать строковый литерал в кавычках."""
        quote = self._peek()
        self._i += 1
        chars: list[str] = []
        while True:
            char = self._peek()
            if char == "":
                raise self._error("Незакрытая строковая константа")
            if char == quote:
                self._i += 1
                return "".join(chars)
            if char == "\\":
                self._i += 1
                escape = self._peek()
                if escape == "":
                    raise self._error("Незакрытая строковая константа")
                if escape not in STRING_ESCAPES:
                    raise self._error(
                        f"Неизвестная управляющая последовательность '\\{escape}'"
                    )
                chars.append(STRING_ESCAPES[escape])
                self._i += 1
                continue
            chars.append(char)
            self._i += 1


def compile_expression(
    source: str, declared: Iterable[str | tuple[str, Type]] = ()
) -> list[tuple]:
    compiler = Compiler(source, declared)
    compiler.expression()
    if not compiler._at_end():
        raise compiler._error(f"Лишний символ {compiler._peek()!r} после выражения")
    compiler._publish_types()
    return compiler.code


def compile_program(
    source: str, declared: Iterable[str | tuple[str, Type]] = ()
) -> list[tuple]:
    return Compiler(source, declared).program()


def disassemble(code: list[tuple]) -> str:
    lines = []
    for pc, instruction in enumerate(code):
        op, *args = instruction
        rendered = " ".join(str(arg) for arg in args)
        lines.append(f"{pc:04d}  {op:<6}{rendered}")
    return "\n".join(lines)


def _div(left: int, right: int) -> int:
    if right == 0:
        raise CompileRuntimeError("Деление на ноль")
    sign = -1 if (left < 0) != (right < 0) else 1
    return sign * (abs(left) // abs(right))


def _mod(left: int, right: int) -> int:
    if right == 0:
        raise CompileRuntimeError("Деление на ноль")
    return left - _div(left, right) * right


def _fact(value: int) -> int:
    if value < 0:
        raise CompileRuntimeError(f"Факториал отрицательного числа: {value}")
    return math.factorial(value)


def _pop(stack: list, pc: int):
    if not stack:
        raise CompileRuntimeError(f"Стек пуст на инструкции {pc}")
    return stack.pop()


def _as_int(value, role: str) -> int:
    if isinstance(value, Array) or not isinstance(value, int):
        raise CompileRuntimeError(f"{role.capitalize()} должен быть целым числом")
    return value


def _as_array(value) -> Array:
    if not isinstance(value, Array):
        raise CompileRuntimeError("Ожидался массив")
    return value


def _checked_index(array: Array, index: int) -> int:
    if not 0 <= index < len(array.items):
        raise CompileRuntimeError(
            f"Индекс {index} выходит за границы массива "
            f"(размер {len(array.items)})"
        )
    return index


def _element(array: Array, index: int) -> int:
    return array.items[_checked_index(array, index)]


def _apply(op: str, left, right):
    if isinstance(left, Array) or isinstance(right, Array):
        raise CompileRuntimeError(f"Операция {op} не применима к массиву")
    if isinstance(left, str) or isinstance(right, str):
        both_strings = isinstance(left, str) and isinstance(right, str)
        if op == "ADD" and both_strings:
            return left + right
        if op in COMPARISON_OPCODES and both_strings:
            return BINARY_OPS[op](left, right)
        raise CompileRuntimeError(f"Операция {op} не применима к строке")
    if op == "DIV":
        # Целочисленное деление — только для целых, иначе обычное.
        if isinstance(left, int) and isinstance(right, int):
            return _div(left, right)
        return left / right
    if op == "MOD":
        return _mod(left, right)
    if op == "POW":
        if right < 0:
            raise CompileRuntimeError("Отрицательная степень")
    return BINARY_OPS[op](left, right)


class Machine:
    """Пошаговый исполнитель байт-кода.

    Машина не знает ничего про GUI: она лишь хранит состояние и умеет
    выполнить одну инструкцию (`step`) или всё сразу (`run`).
    """

    def __init__(
        self,
        code: list[tuple],
        variables: dict | None = None,
        functions: dict | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> None:
        self.code = code
        self.variables = {} if variables is None else variables
        self._initial_variables = dict(self.variables)
        self.functions = dict(BUILTIN_FUNCTIONS)
        if functions:
            self.functions.update(functions)
        self.max_steps = max_steps
        self.stack: list = []
        self.pc = 0
        self.steps = 0
        self.status = "ready"
        self.error: CompileRuntimeError | None = None
        self.result: int | float | str | Array | None = None
        self.last_instruction: tuple | None = None
        self.output: list[str] = []

    def reset(self) -> None:
        self.variables.clear()
        self.variables.update(self._initial_variables)
        self.stack = []
        self.pc = 0
        self.steps = 0
        self.status = "ready"
        self.error = None
        self.result = None
        self.last_instruction = None
        self.output = []

    def _fail(self, error: CompileRuntimeError) -> None:
        self.error = error
        self.status = "error"

    def _finish(self) -> None:
        if len(self.stack) > 1:
            self._fail(
                CompileRuntimeError(
                    f"В конце выполнения стек содержит {len(self.stack)} значений"
                )
            )
            return
        self.result = self.stack[0] if self.stack else None
        self.status = "finished"

    def step(self) -> bool:
        """Выполнить одну инструкцию. False — выполнение остановлено."""
        if self.status in ("finished", "error"):
            return False
        if self.pc >= len(self.code):
            self._finish()
            return False
        if self.steps >= self.max_steps:
            self._fail(
                CompileRuntimeError(
                    "Превышен лимит шагов выполнения (возможен бесконечный цикл)"
                )
            )
            return False

        instruction = self.code[self.pc]
        self.last_instruction = instruction
        self.steps += 1
        try:
            self._execute(instruction)
        except CompileRuntimeError as error:
            self._fail(error)
            return False
        except Exception as error:  # защита GUI от неожиданных ошибок
            self._fail(CompileRuntimeError(f"Ошибка выполнения: {error}"))
            return False

        if self.pc >= len(self.code):
            self._finish()
        elif self.status not in ("finished", "error"):
            self.status = "paused"
        return self.status not in ("finished", "error")

    def run(self) -> int | Array | None:
        if self.error is not None:
            raise self.error
        if self.status == "finished":
            return self.result
        self.status = "running"
        while self.status not in ("finished", "error"):
            if not self.step():
                break
        if self.error is not None:
            raise self.error
        return self.result

    def snapshot(self) -> dict:
        return {
            "pc": self.pc,
            "code_len": len(self.code),
            "stack": list(self.stack),
            "variables": dict(self.variables),
            "steps": self.steps,
            "status": self.status,
            "error": str(self.error) if self.error else None,
            "result": self.result,
            "instruction": self.last_instruction,
            "output": list(self.output),
        }

    def _execute(self, instruction: tuple) -> None:
        op = instruction[0]
        stack = self.stack
        if op == "PUSH":
            stack.append(instruction[1])
            self.pc += 1
        elif op == "LOAD":
            name = instruction[1]
            if name not in self.variables:
                raise CompileRuntimeError(f"Переменная '{name}' не объявлена")
            stack.append(self.variables[name])
            self.pc += 1
        elif op == "STORE":
            self.variables[instruction[1]] = _pop(stack, self.pc)
            self.pc += 1
        elif op == "DECL":
            name = instruction[1]
            if name in self.variables:
                raise CompileRuntimeError(f"Переменная '{name}' уже объявлена")
            self.variables[name] = _pop(stack, self.pc)
            self.pc += 1
        elif op == "NEWARR":
            size = _as_int(_pop(stack, self.pc), "размер массива")
            if size < 0:
                raise CompileRuntimeError(f"Отрицательный размер массива: {size}")
            kind = instruction[1] if len(instruction) > 1 else "int"
            fill = ARRAY_FILL.get(kind, 0)
            stack.append(Array(items=[fill] * size))
            self.pc += 1
        elif op == "MKARR":
            count = instruction[1]
            items = [stack.pop() for _ in range(count)][::-1]
            stack.append(Array(items))
            self.pc += 1
        elif op == "INDEX":
            index = _as_int(_pop(stack, self.pc), "индекс")
            array = _as_array(_pop(stack, self.pc))
            stack.append(_element(array, index))
            self.pc += 1
        elif op == "SETIDX":
            value = _pop(stack, self.pc)
            index = _as_int(_pop(stack, self.pc), "индекс")
            array = _as_array(_pop(stack, self.pc))
            array.items[_checked_index(array, index)] = value
            self.pc += 1
        elif op == "CONVERT":
            kind = instruction[1]
            stack.append(CONVERTERS[kind](_pop(stack, self.pc)))
            self.pc += 1
        elif op == "PRINT":
            count = instruction[1]
            values = [_pop(stack, self.pc) for _ in range(count)][::-1]
            self.output.append(" ".join(_render(value) for value in values))
            stack.append(0)
            self.pc += 1
        elif op == "POP":
            _pop(stack, self.pc)
            self.pc += 1
        elif op == "NEG":
            value = _pop(stack, self.pc)
            if isinstance(value, Array) or not isinstance(value, (int, float)):
                raise CompileRuntimeError(
                    "Унарный минус применим только к числам"
                )
            stack.append(-value)
            self.pc += 1
        elif op == "NOT":
            stack.append(0 if _pop(stack, self.pc) else 1)
            self.pc += 1
        elif op == "JZ":
            if not _pop(stack, self.pc):
                self.pc = instruction[1]
            else:
                self.pc += 1
        elif op == "JMP":
            self.pc = instruction[1]
        elif op == "CALL":
            name, argc = instruction[1], instruction[2]
            if name not in self.functions:
                raise CompileRuntimeError(f"Функция '{name}' не найдена")
            args = [_pop(stack, self.pc) for _ in range(argc)][::-1]
            try:
                value = self.functions[name](*args)
            except CompileRuntimeError:
                raise
            except Exception as error:
                raise CompileRuntimeError(
                    f"Ошибка в функции '{name}': {error}"
                ) from error
            stack.append(value)
            self.pc += 1
        elif op == "FACT":
            value = _pop(stack, self.pc)
            if isinstance(value, Array):
                raise CompileRuntimeError("Факториал не применим к массиву")
            stack.append(_fact(value))
            self.pc += 1
        elif op in BINARY_OPS:
            right, left = _pop(stack, self.pc), _pop(stack, self.pc)
            stack.append(_apply(op, left, right))
            self.pc += 1
        else:
            raise CompileRuntimeError(f"Неизвестная инструкция {op!r} (PC {self.pc})")


def execute(
    code: list[tuple],
    variables: dict | None = None,
    functions: dict | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> int | float | str | Array | None:
    """Выполнить код целиком и вывести накопленный вывод ``print``.

    Вывод печатается даже если выполнение прервалось ошибкой: то, что
    программа напечатала до ошибки, не должно потеряться.
    """
    machine = Machine(code, variables, functions, max_steps)
    try:
        return machine.run()
    finally:
        for line in machine.output:
            print(line)


def _looks_like_program(source: str) -> bool:
    stripped = source.lstrip()
    if stripped.startswith("{") or ";" in stripped:
        return True
    for word in KEYWORDS:
        if stripped.startswith(word):
            nxt = stripped[len(word) : len(word) + 1]
            if nxt == "" or not (nxt.isalnum() or nxt == "_"):
                return True
    return bool(re.match(r"[A-Za-z_]\w*\s*=(?!=)", stripped))


def _render(value) -> str:
    return repr(value) if isinstance(value, Array) else str(value)


def main(argv: list[str]) -> int:
    run = "--run" in argv[1:]
    args = [a for a in argv[1:] if a != "--run"]
    if not args:
        print(
            "Использование: stack_compiler.py [--run имя=значение ...] "
            "<выражение | программа>"
        )
        return 2
    source = args[-1]
    variables: dict = {}
    for arg in args[:-1]:
        name, _, value = arg.partition("=")
        variables[name] = int(value)
    program = _looks_like_program(source)
    try:
        code = (
            compile_program(source, declared=variables.keys())
            if program
            else compile_expression(source, declared=variables.keys())
        )
    except CompileError as error:
        print(f"Ошибка компиляции: {error.message}")
        print(error)
        return 1
    print(disassemble(code))
    if run:
        try:
            result = execute(code, variables)
        except CompileRuntimeError as error:
            print(f"Ошибка выполнения: {error}")
            return 1
        if result is not None:
            print(f"Результат: {result}")
        if program:
            rendered = ", ".join(
                f"{k}={_render(v)}" for k, v in sorted(variables.items())
            )
            print(f"Переменные: {rendered if rendered else 'нет'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))