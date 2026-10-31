import pytest

from stack_compiler import (
    CompileError,
    CompileRuntimeError,
    Machine,
    _mod,
    compile_expression,
    compile_program,
    execute,
)


def run_machine(code):
    machine = Machine(code)
    while machine.step():
        pass
    return machine


def test_machine_steps_expression_until_finished():
    machine = Machine(compile_expression("1 + 2 * 3"))
    assert machine.status == "ready"
    while machine.step():
        pass
    assert machine.status == "finished"
    assert machine.result == 7
    assert machine.steps == 5
    assert machine.stack == [7]


def test_machine_snapshot_contains_state():
    machine = Machine(compile_expression("1 + 2"))
    machine.step()
    view = machine.snapshot()
    assert view["stack"] == [1]
    assert view["pc"] == 1
    assert view["steps"] == 1
    assert view["status"] == "paused"
    assert view["code_len"] == 3


def test_machine_reset_restores_initial_variables():
    variables = {"x": 10}
    machine = Machine(compile_program("x = x + 1; y = 5;"), variables)
    machine.run()
    assert variables == {"x": 11, "y": 5}
    machine.reset()
    assert machine.variables == {"x": 10}
    assert machine.stack == []
    assert machine.steps == 0
    assert machine.status == "ready"


def test_machine_runtime_error_is_stored_and_raised():
    machine = Machine(compile_expression("1 / 0"))
    while machine.step():
        pass
    assert machine.status == "error"
    assert "Деление на ноль" in str(machine.error)
    with pytest.raises(CompileRuntimeError, match="Деление на ноль"):
        machine.run()


def test_machine_host_exception_is_wrapped():
    machine = Machine(compile_expression("sqrt(-1)"))
    with pytest.raises(CompileRuntimeError, match="Ошибка в функции 'sqrt'"):
        machine.run()


def test_machine_max_steps():
    machine = Machine(compile_program("while 1 { }"), max_steps=20)
    with pytest.raises(CompileRuntimeError, match="бесконечный цикл"):
        machine.run()
    assert machine.status == "error"


def test_mod_is_c_style_and_rejects_zero():
    assert execute(compile_expression("7 % 2")) == 1
    assert execute(compile_expression("-7 % 2")) == -1
    assert execute(compile_expression("7 % -2")) == 1
    assert execute(compile_expression("-7 % -2")) == -1
    assert _mod(7, 2) == 1
    with pytest.raises(CompileRuntimeError, match="Деление на ноль"):
        _mod(1, 0)


def test_code_buffer_maps_instructions_to_source_lines():
    code = compile_program("x = 1;\ny = 2;")
    assert code.lines == [1, 1, 2, 2]


def test_compile_error_after_trailing_newline_has_position():
    with pytest.raises(CompileError) as exc:
        compile_expression("1 +\n")
    assert (exc.value.line, exc.value.column) == (2, 1)


def test_top_level_block_is_a_statement():
    result, variables = None, {}
    code = compile_program("{ a = 1; } b = a + 1;")
    execute(code, variables)
    assert variables == {"a": 1, "b": 2}


def test_factorial_binds_tighter_than_unary_prefix():
    assert execute(compile_expression("-3!")) == -6
    assert execute(compile_expression("!0!")) == 0
