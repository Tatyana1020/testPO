"""Проверки встроенной функции ``time()`` и ожидания по времени в горутинах.

``time()`` возвращает показания монотонных часов в секундах (``double``):
смысл имеет только разность двух вызовов. Главная проверка — процедура,
которая в цикле опрашивает время и ждёт одну секунду: две такие горутины
работают одновременно и вместе занимают около секунды, а не две.
"""

import time

import pytest

from stack_compiler import CompileError, compile_program, execute


def run(source: str) -> dict:
    """Выполнить программу и вернуть её глобальные переменные."""
    variables: dict = {}
    execute(compile_program(source), variables)
    return variables


#: Процедура ждёт секунду: в цикле сверяет текущее время с моментом старта.
WAIT_SECOND = """
func int wait_second() {
    double start = time();
    while time() - start < 1.0 { }
    return 1;
}
"""


# --------------------------------------------------------------------------
# time()
# --------------------------------------------------------------------------


def test_time_returns_double():
    assert isinstance(run("double t = time();")["t"], float)


def test_time_does_not_go_backwards():
    source = "double a = time(); double b = time(); int ok = b >= a;"
    assert run(source)["ok"] == 1


@pytest.mark.parametrize(
    "source, fragment",
    [
        ("time(1);", "ожидает 0 аргументов, получено 1"),
        ("int t = time();", "должен иметь тип int, получено double"),
        ("func int time() { return 0; }", "совпадает со встроенной функцией"),
    ],
)
def test_time_compile_errors(source, fragment):
    with pytest.raises(CompileError, match=fragment):
        compile_program(source)


# --------------------------------------------------------------------------
# ожидание секунды в двух потоках
# --------------------------------------------------------------------------


def test_wait_second_in_two_threads_takes_about_one_second():
    # Потоки ждут одновременно: если бы они шли по очереди, вышло бы 2 с.
    source = WAIT_SECOND + """
        double t0 = time();
        go a = wait_second();
        go b = wait_second();
        sync();
        double elapsed = time() - t0;
    """
    started = time.perf_counter()
    variables = run(source)
    wall = time.perf_counter() - started
    assert 1.0 <= variables["elapsed"] <= 1.5   # как измерила сама программа
    assert 1.0 <= wall <= 1.5                   # как измерил Python снаружи
