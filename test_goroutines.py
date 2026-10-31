"""Проверки горутин: ``go``, ``sync()`` и ``kill()``.

Горутина — это функция, запущенная в фоне: отдельная машина в отдельном
потоке. Она делит с родителем только код и список вывода; переменные у неё
свои.
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


SPIN = "func int spin() { int i = 0; while 1 { i = i + 1; } return i; }"
COUNT = (
    "func int count(int n) { int i = 0; int s = 0; "
    "while i < n { s = s + i; i = i + 1; } return s; }"
)


# --------------------------------------------------------------------------
# запуск
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        f"{COUNT} go w = count(100); sync();",
        f"{COUNT} go count(10); sync();",
        f'{COUNT} go w = count(10); sync("w");',
    ],
)
def test_go_starts_a_goroutine(source):
    assert run(source) == {}


def test_named_goroutine_is_registered():
    machine = Machine(compile_program(f"{COUNT} go worker = count(10);"))
    while machine.step():
        if machine.snapshot()["goroutines"]:
            break
    names = [g["name"] for g in machine.snapshot()["goroutines"]]
    assert names == ["worker"]


def test_go_statement_generates_expected_code():
    code = compile_program(f"{COUNT} go w = count(10);")
    assert ("GO", "w", "count", 1) in code


# --------------------------------------------------------------------------
# ожидание: sync
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        f"{COUNT} go w = count(10); sync();",
        f'{COUNT} go w = count(10); sync("w");',
        f'{COUNT} string name = "w"; go w = count(10); sync(name);',
        "sync();",
    ],
)
def test_sync_waits_for_goroutines(source):
    run(source)


def test_sync_by_name_keeps_globals():
    assert run(
        f'{COUNT} string name = "w"; go w = count(10); sync(name);'
    ) == {"name": "w"}


def test_sync_does_not_block_the_step():
    # sync() опрашивает состояние горутин, а не блокирует поток.
    machine = Machine(compile_program(f"{SPIN} go w = spin(); sync();"))
    machine.step()
    machine.step()
    assert machine.status in ("waiting", "paused")


# --------------------------------------------------------------------------
# остановка: kill
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        f'{SPIN} go w = spin(); kill("w");',
        f"{SPIN} go a = spin(); go b = spin(); kill();",
        f'{COUNT} go w = count(1); sync("w"); kill("w");',
        f'{SPIN} string name = "w"; go w = spin(); kill(name);',
    ],
)
def test_kill_stops_goroutines(source):
    run(source)


def test_kill_keeps_globals():
    assert run(
        f'{SPIN} string name = "w"; go w = spin(); kill(name);'
    ) == {"name": "w"}


# --------------------------------------------------------------------------
# вывод и состояние
# --------------------------------------------------------------------------


def test_goroutine_output_goes_to_shared_output():
    machine = Machine(
        compile_program(
            'func int hello() { print("из горутины"); return 0; } '
            "go w = hello(); sync();"
        )
    )
    machine.run()
    assert "из горутины" in machine.output


def test_goroutine_updates_global_variables():
    # Горутина делит глобальные переменные с программой.
    assert run(
        "int total = 0; "
        "func int add(int n) { total = total + n; return total; } "
        "go w = add(5); sync();"
    ) == {"total": 5}


def test_goroutine_has_its_own_variables():
    # У горутины своя область — как у обычного вызова функции.
    machine = Machine(
        compile_program(
            "func int f(int a) { int local = a; return local; } "
            "go w = f(5); sync();"
        )
    )
    machine.run()
    assert machine.variables == {}


# --------------------------------------------------------------------------
# ошибки компиляции
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, fragment",
    [
        ("go w = нет(1);", "нужна пользовательская функция"),
        (f"{COUNT} go w = count(1, 2);", "ожидает 1 аргумент"),
        (f'{COUNT} go w = count("строка");', "Аргумент 1 функции 'count'"),
    ],
)
def test_go_compile_errors(source, fragment):
    with pytest.raises(CompileError, match=fragment):
        compile_program(source)


# --------------------------------------------------------------------------
# ошибки рантайма
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, fragment",
    [
        ('sync("нет");', "не найдена"),
        ('kill("нет");', "не найдена"),
        (f'{COUNT} go w = count(1); go w = count(1);', "уже существует"),
        (
            "func int bad() { int x = 1 / 0; return x; } go w = bad(); sync();",
            "Деление на ноль",
        ),
        (
            "func int bad() { int x = 1 / 0; return x; } go w = bad();",
            "Деление на ноль",
        ),
    ],
)
def test_goroutine_runtime_errors(source, fragment):
    with pytest.raises(CompileRuntimeError, match=fragment):
        run(source)


def test_goroutine_hits_step_limit():
    with pytest.raises(CompileRuntimeError, match="лимит шагов"):
        run(
            "func int spin() { int i = 0; while 1 { i = i + 1; } return i; } "
            "go w = spin(); sync();"
        )


# --------------------------------------------------------------------------
# сброс и вложенность
# --------------------------------------------------------------------------


def test_reset_stops_goroutines():
    machine = Machine(compile_program(f"{SPIN} go w = spin();"))
    machine.step()
    machine.step()
    assert machine.goroutines.all()
    machine.reset()
    assert all(g.killed for g in machine.goroutines.all())


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            f"{COUNT} func int outer() {{ go w = count(10); return 1; }} "
            "int x = outer(); sync();",
            {"x": 1},
        ),
    ],
)
def test_go_inside_function(source, expected):
    assert run(source) == expected


def test_goroutine_started_inside_function_is_joined_by_sync():
    # Реестр горутин общий: sync() ждёт и «внуков» тоже.
    machine = Machine(
        compile_program(
            "func int inner() { int i = 0; int s = 0; while i < 100 "
            "{ s = s + i; i = i + 1; } return s; } "
            "func int outer() { go w = inner(); return 1; } "
            "int x = outer(); sync();"
        )
    )
    machine.run()
    assert machine.status == "finished"
