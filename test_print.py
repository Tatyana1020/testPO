"""Проверки функции ``print`` и канала вывода.

``print`` печатает значения в канал машины (``Machine.output``). В CLI
вывод печатается на stdout, в GUI — попадает в панель вывода.
"""

import pytest

from stack_compiler import (
    CompileError,
    Machine,
    compile_expression,
    compile_program,
    execute,
)


def run(source: str) -> list[str]:
    """Выполнить программу и вернуть напечатанные строки."""
    machine = Machine(compile_program(source))
    machine.run()
    return list(machine.output)


def test_print_writes_to_machine_output():
    assert run('print("привет");') == ["привет"]


def test_print_several_arguments_are_space_separated():
    assert run('print(1, 2, "три");') == ["1 2 три"]


def test_print_without_arguments_gives_empty_line():
    assert run("print();") == [""]


def test_print_appends_a_line_per_call():
    assert run('print("a"); print("b");') == ["a", "b"]


def test_print_of_a_number():
    assert run("print(42);") == ["42"]


def test_print_of_a_real_number():
    assert run("print(1.5);") == ["1.5"]


def test_print_of_a_string_does_not_add_quotes():
    assert run('print("abc");') == ["abc"]


def test_print_of_an_array():
    assert run("int a[2]; a[0] = 7; print(a);") == ["[7, 0]"]


def test_print_of_a_string_array():
    assert run('string s[2]; s[0] = "a"; print(s);') == ["['a', '']"]


def test_print_returns_zero():
    assert execute(compile_expression("print(1)")) == 0


def test_print_is_available_in_expression_mode():
    machine = Machine(compile_expression('print("в выражении")'))
    machine.run()
    assert machine.output == ["в выражении"]


def test_execute_prints_output_to_stdout(capsys):
    execute(compile_program('print("в stdout");'))
    assert "в stdout" in capsys.readouterr().out


def test_execute_prints_output_even_when_execution_fails(capsys):
    with pytest.raises(Exception):
        execute(compile_program('print("до ошибки"); int x = 1 / 0;'))
    assert "до ошибки" in capsys.readouterr().out


def test_output_is_cleared_on_reset():
    machine = Machine(compile_program('print("строка");'))
    machine.run()
    assert machine.output == ["строка"]
    machine.reset()
    assert machine.output == []


def test_output_is_part_of_snapshot():
    machine = Machine(compile_program('print("строка");'))
    machine.run()
    assert machine.snapshot()["output"] == ["строка"]


def test_print_accepts_any_type():
    assert run('double d = 1.5; string s = "x"; print(d, s);') == ["1.5 x"]


def test_print_argument_count_is_not_checked():
    assert run("print(1, 2, 3, 4, 5);") == ["1 2 3 4 5"]


def test_print_instruction_is_generated():
    assert compile_program("print(1, 2);") == [
        ("PUSH", 1), ("PUSH", 2), ("PRINT", 2), ("POP",),
    ]
