"""Проверки пользовательских функций.

Синтаксис определения: ``func int f(int a, int b) { return a + b; }``.
У функции своя область: внешние переменные внутри неё не видны, локальные
не видны снаружи.
"""

import pytest

from stack_compiler import (
    CompileError,
    CompileRuntimeError,
    Machine,
    compile_program,
    execute,
)


def run(source: str) -> dict:
    """Выполнить программу и вернуть её глобальные переменные."""
    variables: dict = {}
    execute(compile_program(source), variables)
    return variables


# --------------------------------------------------------------------------
# вызов: результат, параметры, контекст
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        ("func int two() { return 2; } int x = two();", {"x": 2}),
        ("func int answer() { return 42; } int x = answer();", {"x": 42}),
        (
            "func int add(int a, int b) { return a + b; } int x = add(2, 3);",
            {"x": 5},
        ),
        ("func int two() { return 2; } int x = two() * 10 + 1;", {"x": 21}),
        (
            'func string greet(string name) { return "привет, " + name; } '
            'string s = greet("мир");',
            {"s": "привет, мир"},
        ),
        (
            "func double half(double x) { return x / 2; } double d = half(5.0);",
            {"d": 2.5},
        ),
        (
            # аргумент неявно расширяется до типа параметра
            "func double half(double x) { return x / 2; } double d = half(5);",
            {"d": 2.5},
        ),
        ("func int f() { } int x = f();", {"x": 0}),
        ("func int f() { return; } int x = f();", {"x": 0}),
    ],
)
def test_function_call(source, expected):
    assert run(source) == expected


def test_function_definition_is_compiled():
    # Тело функции пропускается: JMP перепрыгивает его, за ним RET.
    assert compile_program("func int f(int a) { return a; }") == [
        ("JMP", 5),
        ("LOAD", "a"),
        ("RET",),
        ("PUSH", 0),
        ("RET",),
    ]


def test_function_call_uses_separate_opcode():
    # Пользовательские функции вызываются инструкцией CALLF, встроенные —
    # обычной CALL.
    code = compile_program("func int f() { return 1; } int x = f();")
    assert ("CALLF", "f", 0) in code
    assert not [item for item in code if item[0] == "CALL"]


# --------------------------------------------------------------------------
# рекурсия
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "func int fact(int n) { if n <= 1 { return 1; } "
            "return n * fact(n - 1); } int x = fact(5);",
            {"x": 120},
        ),
        (
            # каждый вызов получает свои локальные переменные
            "func int depth(int n) { if n <= 0 { return 0; } "
            "int local = n; return local + depth(n - 1); } int x = depth(3);",
            {"x": 6},
        ),
        (
            "func int fib(int n) { if n < 2 { return n; } "
            "return fib(n - 1) + fib(n - 2); } int x = fib(10);",
            {"x": 55},
        ),
    ],
)
def test_recursion(source, expected):
    assert run(source) == expected


# --------------------------------------------------------------------------
# область видимости
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            # локальная переменная не выходит наружу
            "func int f() { int local = 5; return local; } int x = f();",
            {"x": 5},
        ),
        (
            # два вызова не мешают друг другу
            "func int f(int a) { int local = a * 2; return local; } "
            "int x = f(1); int y = f(10);",
            {"x": 2, "y": 20},
        ),
    ],
)
def test_function_locals_are_isolated(source, expected):
    assert run(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        # функция видит глобальные переменные
        ("int n = 5; func int f() { return n; } int x = f();", {"n": 5, "x": 5}),
        # и может их менять
        (
            "int total = 0; func int f() { total = 7; return 0; } int x = f();",
            {"total": 7, "x": 0},
        ),
        # цикл по глобальным переменным — как в примере из документации
        (
            "int n = 5; int result = 1; int i = 1; "
            "func int f() { while i <= n { result = result * i; i = i + 1; } "
            "return result; } int x = f();",
            {"n": 5, "result": 120, "i": 6, "x": 120},
        ),
    ],
)
def test_function_sees_global_variables(source, expected):
    assert run(source) == expected


def test_global_must_be_declared_before_the_function():
    # Компилятор одноходовый: глобальная должна быть объявлена раньше.
    with pytest.raises(CompileError, match="не объявлена"):
        compile_program("func int f() { return n; } int n = 5;")


def test_local_shadows_global():
    # Локальное имя перекрывает глобальное, но глобальное не меняется.
    assert run(
        "int x = 1; func int f() { int x = 99; return x; } int y = f();"
    ) == {"x": 1, "y": 99}


def test_machine_scope_is_restored_after_call():
    machine = Machine(compile_program("func int f() { return 1; } int x = f();"))
    machine.run()
    assert machine.frames == []
    assert machine.variables == {"x": 1}


def test_reset_restores_globals_after_call():
    variables = {"x": 10}
    machine = Machine(
        compile_program("func int f() { return 1; } int y = f();"), variables
    )
    machine.run()
    machine.reset()
    assert machine.variables == {"x": 10}
    assert machine.frames == []


# --------------------------------------------------------------------------
# ошибки компиляции
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, fragment",
    [
        (
            'func int f() { return "строка"; }',
            "Значение функции 'f' должно иметь тип int",
        ),
        ("return 1;", "только внутри функции"),
        ("func int f(int a) { return a; } f(1, 2);", "ожидает 1 аргумент"),
        (
            "func int f(int a, int b) { return a + b; } f(1);",
            "ожидает 2 аргумента",
        ),
        (
            'func int f(int a) { return a; } f("строка");',
            "Аргумент 1 функции 'f'",
        ),
        ("int x = f(); func int f() { return 1; }", "раньше объявления"),
        (
            "func int f() { return 1; } func int f() { return 2; }",
            "уже объявлена",
        ),
        ("func int abs(int x) { return x; }", "встроенной функцией"),
        ("func int sync() { return 1; }", "зарезервировано"),
        (
            "func int f() { func int g() { return 1; } return 1; }",
            "только на верхнем уровне",
        ),
        ("func int f(int a, int a) { return a; }", "дважды"),
        ("func f() { return 1; }", "тип возвращаемого значения"),
    ],
)
def test_function_compile_errors(source, fragment):
    with pytest.raises(CompileError, match=fragment):
        compile_program(source)


# --------------------------------------------------------------------------
# ошибки рантайма
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, fragment",
    [
        ([("CALLF", "нет", 0)], "не найдена"),
        ([("RET",)], "вне функции"),
    ],
)
def test_function_runtime_errors(code, fragment):
    with pytest.raises(CompileRuntimeError, match=fragment):
        execute(code)


def test_unknown_function_is_still_allowed():
    # Внешние Python-функции по-прежнему можно подставить при запуске.
    variables: dict = {}
    execute(
        compile_program("int x = twice(21);"),
        variables,
        {"twice": lambda v: 2 * v},
    )
    assert variables == {"x": 42}
