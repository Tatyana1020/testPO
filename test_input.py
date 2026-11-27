"""Проверки функции ``input`` и канала ввода.

``input()`` читает строку из очереди машины или из источника ввода. В GUI
машина не блокируется: она встаёт в состояние ``waiting_input``, пока
пользователь не передаст строку через ``provide_input``. В CLI строку
читает stdin.
"""

import io
import time
from collections import deque

import pytest

from gui.controller import DebugSession
from stack_compiler import (
    CompileError,
    CompileRuntimeError,
    Machine,
    compile_expression,
    compile_program,
    execute,
    main,
)


def make_machine(source: str, **kwargs) -> Machine:
    return Machine(compile_program(source), **kwargs)


def run_with_input(source: str, *lines: str) -> Machine:
    machine = make_machine(source)
    for line in lines:
        machine.provide_input(line)
    machine.run()
    return machine


# --------------------------------------------------------------------------
# компиляция
# --------------------------------------------------------------------------


def test_input_instruction_is_generated():
    assert compile_program("string s = input();") == [
        ("INPUT", 0),
        ("DECL", "s"),
    ]


def test_input_prompt_instruction_is_generated():
    assert compile_program('string s = input("Имя: ");') == [
        ("PUSH", "Имя: "),
        ("INPUT", 1),
        ("DECL", "s"),
    ]


def test_input_returns_string():
    assert run_with_input("string s = input(); print(s);", "привет").output == [
        "привет"
    ]


def test_input_prompt_is_printed_before_the_value():
    machine = run_with_input(
        'string s = input("Имя: "); print("Привет,", s);', "Аня"
    )
    assert machine.output == ["Имя: ", "Привет, Аня"]


def test_input_reads_lines_in_order():
    machine = run_with_input(
        "string a = input(); string b = input(); print(a, b);", "раз", "два"
    )
    assert machine.variables == {"a": "раз", "b": "два"}
    assert machine.output == ["раз два"]


def test_input_conversion_to_int():
    machine = run_with_input("int n = int(input()); print(n + 1);", "41")
    assert machine.variables == {"n": 41}
    assert machine.output == ["42"]


def test_input_in_expression_mode():
    machine = Machine(compile_expression("input()"))
    machine.provide_input("значение")
    assert machine.run() == "значение"


def test_input_without_conversion_is_a_type_error():
    with pytest.raises(CompileError, match="должен иметь тип int"):
        compile_program("int n = input();")


def test_input_prompt_must_be_string():
    with pytest.raises(CompileError, match="должен иметь тип string"):
        compile_program("input(1);")


def test_input_accepts_at_most_one_argument():
    with pytest.raises(CompileError, match="не более 1 аргумента"):
        compile_program('input("a", "b");')


# --------------------------------------------------------------------------
# ожидание ввода
# --------------------------------------------------------------------------


def test_input_waits_without_a_source():
    machine = make_machine("string s = input();")
    assert machine.step() is False
    assert machine.status == "waiting_input"
    assert machine.pc == 0
    assert machine.steps == 0
    assert machine.last_instruction == ("INPUT", 0)


def test_waiting_input_does_not_consume_the_step_limit():
    machine = make_machine("string s = input();")
    for _ in range(5):
        machine.step()
    assert machine.status == "waiting_input"
    assert machine.steps == 0


def test_repeated_step_does_not_duplicate_the_prompt():
    machine = make_machine('string s = input("Имя: ");')
    machine.step()       # PUSH "Имя: "
    for _ in range(5):
        machine.step()   # INPUT всё ещё ждёт
    assert machine.output == ["Имя: "]


def test_input_prompt_is_available_while_waiting():
    machine = make_machine('string s = input("Имя: ");')
    assert machine.step() is True          # PUSH "Имя: "
    assert machine.step() is False         # INPUT ждёт
    assert machine.status == "waiting_input"
    assert machine.input_prompt == "Имя: "
    assert machine.output == ["Имя: "]


def test_provide_input_wakes_the_machine():
    machine = make_machine("string s = input();")
    machine.step()
    assert machine.status == "waiting_input"
    machine.provide_input("строка")
    assert machine.status == "paused"
    machine.run()
    assert machine.variables == {"s": "строка"}


def test_provide_input_accepts_an_empty_line():
    machine = run_with_input("string s = input(); print(s == \"\");", "")
    assert machine.variables == {"s": ""}
    assert machine.output == ["1"]


def test_input_lines_can_be_seeded():
    machine = Machine(
        compile_program("string s = input();"),
        input_lines=deque(["заранее"]),
    )
    machine.run()
    assert machine.variables == {"s": "заранее"}


def test_reset_clears_pending_input_and_prompt():
    machine = make_machine('string s = input("Имя: ");')
    machine.step()
    machine.step()
    assert machine.status == "waiting_input"
    machine.provide_input("не пригодится")
    machine.reset()
    assert machine.status == "ready"
    assert list(machine.input_lines) == []
    assert machine.input_prompt is None


def test_snapshot_contains_input_state():
    machine = make_machine('string s = input("Имя: ");')
    machine.step()
    machine.step()
    view = machine.snapshot()
    assert view["status"] == "waiting_input"
    assert view["input_prompt"] == "Имя: "
    assert view["input_pending"] == 0


def test_goroutine_reads_from_the_shared_input_queue():
    machine = run_with_input(
        """func int read() { string s = input(); print(s); return 0; }
go read();
sync();
print("готово");
""",
        "из горутины",
    )
    assert machine.output == ["из горутины", "готово"]


def test_goroutine_wakes_when_input_arrives_later():
    machine = make_machine(
        """func int read() { string s = input(); print(s); return 0; }
go read();
sync();
"""
    )
    for _ in range(1000):
        machine.step()
        waiter = machine.input_waiter()
        if waiter is not None and waiter is not machine:
            break
        time.sleep(0.001)
    else:
        pytest.fail("горутина так и не начала ждать ввода")
    machine.provide_input("поздно")
    machine.run()
    assert machine.output == ["поздно"]


def test_goroutine_waiting_input_does_not_hang_run():
    machine = make_machine(
        """func int read() { string s = input(); print(s); return 0; }
go read();
print("готово");
"""
    )
    with pytest.raises(CompileRuntimeError, match="Горутина ждёт ввода"):
        machine.run()
    assert machine.status == "error"


def test_sync_with_goroutine_waiting_input_reports_error():
    machine = make_machine(
        """func int read() { string s = input(); print(s); return 0; }
go read();
sync();
"""
    )
    with pytest.raises(CompileRuntimeError, match="Горутина ждёт ввода"):
        machine.run()
    assert machine.status == "error"


# --------------------------------------------------------------------------
# execute и CLI
# --------------------------------------------------------------------------


def test_execute_uses_input_provider(capsys):
    lines = iter(["41"])
    execute(
        compile_program("print(int(input()) + 1);"),
        input_provider=lambda: next(lines, None),
    )
    assert capsys.readouterr().out.splitlines() == ["42"]


def test_execute_flushes_prompt_before_reading(capsys):
    lines = iter(["Аня"])
    execute(
        compile_program('string s = input("Имя: "); print(s);'),
        input_provider=lambda: next(lines, None),
    )
    assert capsys.readouterr().out.splitlines() == ["Имя: ", "Аня"]


def test_execute_reports_eof():
    with pytest.raises(CompileRuntimeError, match="EOF"):
        execute(
            compile_program("string s = input();"),
            input_provider=lambda: None,
        )


def test_cli_reads_input_from_stdin(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("Аня\n"))
    source = 'string name = input("Имя: "); print("Привет,", name);'
    assert main(["stack_compiler.py", "--run", source]) == 0
    out = capsys.readouterr().out
    assert "Имя: " in out
    assert "Привет, Аня" in out


# --------------------------------------------------------------------------
# DebugSession
# --------------------------------------------------------------------------


def test_debug_session_input_roundtrip():
    session = DebugSession()
    assert session.compile(
        'string name = input("Имя: "); print("Привет,", name);'
    )
    while session.step():
        pass
    assert session.waiting_for_input is True
    assert session.input_prompt == "Имя: "
    assert session.provide_input("Аня") is True
    session.run_all()
    assert session.output == ["Имя: ", "Привет, Аня"]
    assert session.status == "finished"


def test_debug_session_provide_input_without_machine():
    session = DebugSession()
    assert session.provide_input("некуда") is False
