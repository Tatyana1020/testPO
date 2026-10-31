import pytest

from stack_compiler import (
    Array,
    CompileError,
    CompileRuntimeError,
    Machine,
    compile_program,
    execute,
)


def run_program(source: str) -> dict:
    variables: dict = {}
    execute(compile_program(source), variables)
    return variables


def test_int_declaration_defaults_to_zero():
    assert run_program("int x;") == {"x": 0}


def test_int_declaration_with_initializer():
    assert run_program("int x = 5;") == {"x": 5}


def test_duplicate_declaration_is_compile_error():
    with pytest.raises(CompileError, match="уже объявлена"):
        compile_program("int x = 1; int x = 2;")


def test_duplicate_declaration_is_still_a_runtime_error():
    # Байт-код, собранный вручную, по-прежнему ловится в рантайме.
    with pytest.raises(CompileRuntimeError, match="уже объявлена"):
        execute([("PUSH", 1), ("DECL", "x"), ("PUSH", 2), ("DECL", "x")])


def test_sized_array_defaults_to_zeros():
    variables = run_program("int a[3];")
    assert isinstance(variables["a"], Array)
    assert variables["a"].items == [0, 0, 0]


def test_array_literal_and_index_read():
    variables = run_program("int a = [1, 2, 3]; int x; x = a[1] + 10;")
    assert variables["a"].items == [1, 2, 3]
    assert variables["x"] == 12


def test_element_assignment_writes_to_the_requested_index():
    variables = run_program(
        "int a[3]; int x; a[0] = 7; a[2] = 9; x = a[0] + a[1] + a[2];"
    )
    assert variables["a"].items == [7, 0, 9]
    assert variables["x"] == 16


def test_resize_extends_and_truncates_array():
    variables = run_program(
        "int a[2]; int x; a[1] = 5; resize(a, 4); a[3] = 7; x = a[1] + a[3];"
    )
    assert variables["a"].items == [0, 5, 0, 7]
    assert variables["x"] == 12

    variables = run_program("int a = [1, 2, 3]; int x; resize(a, 1); x = a[0];")
    assert variables["a"].items == [1]
    assert variables["x"] == 1


def test_empty_array_literal_can_be_resized():
    variables = run_program(
        "int a = []; int x; resize(a, 2); a[1] = 4; x = a[1];"
    )
    assert variables["a"].items == [0, 4]
    assert variables["x"] == 4


def test_index_out_of_bounds_is_runtime_error():
    with pytest.raises(CompileRuntimeError, match="границы"):
        run_program("int a[2]; int x; x = a[2];")


def test_element_assignment_out_of_bounds_is_runtime_error():
    with pytest.raises(CompileRuntimeError, match="границы"):
        run_program("int a[2]; a[2] = 1;")


def test_resize_rejects_negative_size():
    with pytest.raises(CompileRuntimeError, match="отрицательный размер"):
        run_program("int a[2]; resize(a, -1);")


def test_resize_rejects_non_array_argument():
    with pytest.raises(CompileError, match="должен иметь тип массива"):
        compile_program("int x = 1; resize(x, 2);")


def test_negative_array_size_is_runtime_error():
    with pytest.raises(CompileRuntimeError, match="Отрицательный размер"):
        run_program("int a[-1];")


def test_array_size_and_literal_together_is_compile_error():
    with pytest.raises(CompileError, match="одновременно размер"):
        compile_program("int a[3] = [1, 2, 3];")


def test_array_in_arithmetic_is_compile_error():
    with pytest.raises(CompileError, match="не применима к массиву"):
        compile_program("int a[2]; int x; x = a + 1;")


def test_array_in_arithmetic_is_still_a_runtime_error():
    # Байт-код, собранный вручную, по-прежнему ловится в рантайме.
    with pytest.raises(CompileRuntimeError, match="не применима к массиву"):
        execute([("PUSH", 2), ("NEWARR",), ("PUSH", 1), ("ADD",)])


def test_machine_executes_array_opcodes_step_by_step():
    machine = Machine(
        compile_program("int a[2]; int x; a[0] = 5; x = a[0];")
    )
    while machine.step():
        pass
    assert machine.status == "finished"
    assert machine.variables["a"].items == [5, 0]
    assert machine.variables["x"] == 5
