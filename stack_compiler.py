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
    слаг       := множ { ("*" | "/") множ }
    множ       := операнд [ "^" операнд ]
    операнд    := имя | конст | "(" выр ")" | вызов { постфикс }
    постфикс   := "!" | "[" выр "]"
    вызов      := имя "(" [ выр { "," выр } ] ")"

Разбор идёт напрямую по символам исходного текста (лексера нет), дерево
разбора не строится: код стековой машины выпускается по мере разбора,
переходы если/пока дописываются на месте (патчинг адресов).
"""

from __future__ import annotations

import math
import sys

LOGICAL_OPS = ("&&", "||")
COMPARISON_OPS = ("<>", "!=", "<=", ">=", "==", "<", ">")
SUM_OPS = ("+", "-")
TERM_OPS = ("*", "/")
POWER_OPS = ("^",)
PREFIX_OPS = ("+", "-", "!")
KEYWORDS = ("int", "if", "else", "while")

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

BINARY_OPS = {
    "ADD": lambda a, b: a + b,
    "SUB": lambda a, b: a - b,
    "MUL": lambda a, b: a * b,
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
        return "[" + ", ".join(str(item) for item in self.items) + "]"


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


BUILTIN_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "resize": _resize,
}

DEFAULT_MAX_STEPS = 1_000_000


class CompileError(Exception):
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


class Compiler:
    def __init__(self, source: str) -> None:
        self._source = source
        self._i = 0
        self.code: list[tuple] = []

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

    def _starts_inequality(self) -> bool:
        return self._source.startswith("!=", self._i) and not (
            self._source.startswith("!==", self._i)
        )

    def _emit_jump(self, op: str) -> int:
        self.code.append((op, -1))
        return len(self.code) - 1

    def _patch(self, index: int, target: int) -> None:
        self.code[index] = (self.code[index][0], target)

    def program(self) -> list[tuple]:
        while not self._at_end():
            self.statement()
        return self.code

    def statement(self) -> None:
        self._skip()
        if self._match_kw("if"):
            self.if_statement()
            return
        if self._match_kw("while"):
            self.while_statement()
            return
        if self._match_kw("int"):
            self.declaration()
            return
        if self._peek() == "{":
            self.block()
            return
        if self._peek() == ";":
            self._i += 1
            return
        if self._try_element_assignment():
            self.expression()
            self.code.append(("SETIDX",))
            self._skip()
            if not self._at_end():
                self._take_char(";", "';'")
            return
        name = self._try_assignment()
        if name is not None:
            self.expression()
            self.code.append(("STORE", name))
        else:
            self.expression()
            self.code.append(("POP",))
        self._skip()
        if not self._at_end():
            self._take_char(";", "';'")

    def declaration(self) -> None:
        self._skip()
        name = self._ident()
        self._skip()
        has_size = False
        if self._peek() == "[":
            if self._size_followed_by_literal():
                raise self._error(
                    "Массив не может иметь одновременно размер и список "
                    "инициализации"
                )
            self._i += 1
            self.expression()
            self._take_char("]", "']'")
            self.code.append(("NEWARR",))
            has_size = True
            self._skip()
        if self._peek() == "=" and not self._source.startswith("==", self._i):
            self._i += 1
            self._skip()
            if self._peek() == "[":
                self.array_literal()
            else:
                self.expression()
        elif not has_size:
            self.code.append(("PUSH", 0))
        self.code.append(("DECL", name))
        self._take_char(";", "';'")

    def array_literal(self) -> None:
        self._take_char("[", "'['")
        count = 0
        self._skip()
        if self._peek() != "]":
            self.expression()
            count = 1
            while self._match_op((",",)):
                self.expression()
                count += 1
        self._take_char("]", "']'")
        self.code.append(("MKARR", count))

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
        start = self._i
        mark = len(self.code)
        if not (self._peek().isalpha() or self._peek() == "_"):
            return False
        self.code.append(("LOAD", self._ident()))
        self._skip()
        if self._peek() != "[":
            self._i = start
            self.code = self.code[:mark]
            return False
        self._i += 1
        self.expression()
        self._take_char("]", "']'")
        self._skip()
        if self._peek() == "=" and not self._source.startswith("==", self._i):
            self._i += 1
            return True
        self._i = start
        self.code = self.code[:mark]
        return False

    def if_statement(self) -> None:
        jumps: list[int] = []
        while True:
            self.expression()
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
        self.expression()
        jz = self._emit_jump("JZ")
        self.block()
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

    def expression(self) -> None:
        self.comparison()
        while True:
            op = self._match_op(LOGICAL_OPS)
            if not op:
                break
            self.comparison()
            self.code.append((OPCODES[op],))

    def comparison(self) -> None:
        self.sum()
        while True:
            op = self._match_op(COMPARISON_OPS)
            if not op:
                break
            self.sum()
            self.code.append((OPCODES[op],))

    def sum(self) -> None:
        self.term()
        while True:
            op = self._match_op(SUM_OPS)
            if not op:
                break
            self.term()
            self.code.append(("ADD" if op == "+" else "SUB",))

    def term(self) -> None:
        self.power()
        while True:
            op = self._match_op(TERM_OPS)
            if not op:
                break
            self.power()
            self.code.append(("MUL" if op == "*" else "DIV",))

    def power(self) -> None:
        self.operand()
        if self._match_op(POWER_OPS):
            self.operand()
            self.code.append(("POW",))

    def operand(self) -> None:
        prefixes = self._collect_prefix()
        self._skip()
        char = self._peek()
        if char.isalpha() or char == "_":
            name = self._ident()
            self._skip()
            if self._peek() == "(":
                self.call(name)
            else:
                self.code.append(("LOAD", name))
        elif char.isdigit():
            self.code.append(("PUSH", self._number()))
        elif char == "(":
            self._i += 1
            self.expression()
            self._take_char(")", "')'")
        else:
            raise self._error(
                "Ожидался операнд: имя, конст, '(' выр ')' или вызов функции. "
                f"Получено {self._here()}"
            )
        self.postfix()
        for sign in reversed(prefixes):
            if sign == "-":
                self.code.append(("NEG",))
            elif sign == "!":
                self.code.append(("NOT",))

    def call(self, name: str) -> None:
        self._take_char("(", "'('")
        argc = 0
        self._skip()
        if self._peek() != ")":
            self.expression()
            argc += 1
            while self._match_op((",",)):
                self.expression()
                argc += 1
        self._take_char(")", "')'")
        self.code.append(("CALL", name, argc))

    def postfix(self) -> None:
        while True:
            self._skip()
            char = self._peek()
            if char == "[":
                self._i += 1
                self.expression()
                self._take_char("]", "']'")
                self.code.append(("INDEX",))
            elif char == "!" and not self._starts_inequality():
                self._i += 1
                self.code.append(("FACT",))
            else:
                return

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

    def _number(self) -> int:
        start = self._i
        while self._peek().isdigit():
            self._i += 1
        return int(self._source[start : self._i])


def compile_expression(source: str) -> list[tuple]:
    compiler = Compiler(source)
    compiler.expression()
    if not compiler._at_end():
        raise compiler._error(f"Лишний символ {compiler._peek()!r} после выражения")
    return compiler.code


def compile_program(source: str) -> list[tuple]:
    return Compiler(source).program()


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


def _fact(value: int) -> int:
    if value < 0:
        raise CompileRuntimeError(f"Факториал отрицательного числа: {value}")
    return math.factorial(value)


def _pop(stack: list[int], pc: int) -> int:
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
    if op == "DIV":
        return _div(left, right)
    if op == "POW":
        if right < 0:
            raise CompileRuntimeError("Отрицательная степень")
    return BINARY_OPS[op](left, right)


def execute(
    code: list[tuple],
    variables: dict | None = None,
    functions: dict | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> int | None:
    variables = {} if variables is None else variables
    merged = dict(BUILTIN_FUNCTIONS)
    if functions:
        merged.update(functions)
    return _run(code, variables, merged, max_steps)


def _run(code: list[tuple], variables: dict, functions: dict, max_steps: int):
    stack: list[int] = []
    pc = 0
    steps = 0
    while pc < len(code):
        steps += 1
        if steps > max_steps:
            raise CompileRuntimeError(
                "Превышен лимит шагов выполнения (возможен бесконечный цикл)"
            )
        instruction = code[pc]
        op = instruction[0]
        if op == "PUSH":
            stack.append(instruction[1])
        elif op == "LOAD":
            name = instruction[1]
            if name not in variables:
                raise CompileRuntimeError(f"Переменная '{name}' не объявлена")
            stack.append(variables[name])
        elif op == "STORE":
            variables[instruction[1]] = _pop(stack, pc)
        elif op == "DECL":
            name = instruction[1]
            if name in variables:
                raise CompileRuntimeError(f"Переменная '{name}' уже объявлена")
            variables[name] = _pop(stack, pc)
        elif op == "NEWARR":
            size = _as_int(_pop(stack, pc), "размер массива")
            if size < 0:
                raise CompileRuntimeError(f"Отрицательный размер массива: {size}")
            stack.append(Array(size=size))
        elif op == "MKARR":
            count = instruction[1]
            items = [stack.pop() for _ in range(count)][::-1]
            stack.append(Array(items))
        elif op == "INDEX":
            index = _as_int(_pop(stack, pc), "индекс")
            array = _as_array(_pop(stack, pc))
            stack.append(_element(array, index))
        elif op == "SETIDX":
            index = _as_int(_pop(stack, pc), "индекс")
            value = _pop(stack, pc)
            array = _as_array(_pop(stack, pc))
            array.items[_checked_index(array, index)] = value
        elif op == "POP":
            _pop(stack, pc)
        elif op == "NEG":
            stack.append(-_pop(stack, pc))
        elif op == "NOT":
            stack.append(0 if _pop(stack, pc) else 1)
        elif op == "JZ":
            if not _pop(stack, pc):
                pc = instruction[1]
                continue
        elif op == "JMP":
            pc = instruction[1]
            continue
        elif op == "CALL":
            name, argc = instruction[1], instruction[2]
            if name not in functions:
                raise CompileRuntimeError(f"Функция '{name}' не найдена")
            args = [stack.pop() for _ in range(argc)][::-1]
            stack.append(int(functions[name](*args)))
        elif op == "FACT":
            stack.append(_fact(_pop(stack, pc)))
        elif op == "DIV":
            right, left = _pop(stack, pc), _pop(stack, pc)
            stack.append(_div(left, right))
        elif op in BINARY_OPS:
            right, left = _pop(stack, pc), _pop(stack, pc)
            stack.append(_apply(op, left, right))
        else:
            raise CompileRuntimeError(f"Неизвестная инструкция {op!r} (PC {pc})")
        pc += 1
    if len(stack) > 1:
        raise CompileRuntimeError(
            f"В конце выполнения стек содержит {len(stack)} значений"
        )
    return stack[0] if stack else None


def _looks_like_program(source: str) -> bool:
    stripped = source.lstrip()
    if stripped.startswith("{") or ";" in stripped:
        return True
    for word in KEYWORDS:
        if stripped.startswith(word):
            nxt = stripped[len(word) : len(word) + 1]
            if nxt == "" or not (nxt.isalnum() or nxt == "_"):
                return True
    return False


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
        code = compile_program(source) if program else compile_expression(source)
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