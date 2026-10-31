"""Проверки статической системы типов языка Stack Lang.

Типы: ``int`` и ``int[]``. Переменная обязана быть объявлена до первого
использования. Проверки выполняются на этапе компиляции; рантайм-проверки
в ``Machine`` при этом остаются и срабатывают на байт-коде, собранном
вручную.
"""

import pytest

from stack_compiler import (
    CompileError,
    CompileRuntimeError,
    Compiler,
    compile_expression,
    compile_program,
    execute,
)
from stack_types import SymbolTable, Type, normalize_declared


# --------------------------------------------------------------------------
# объявления
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "x = 1;",
        "x = 1; x = x + 1;",
        "y = x;",
        "x + 1",
    ],
)
def test_undeclared_variable_is_rejected(source):
    with pytest.raises(CompileError, match="не объявлена"):
        compile_program(source)


def test_undeclared_variable_error_points_at_the_name():
    with pytest.raises(CompileError) as exc:
        compile_program("x = 1;")
    assert (exc.value.line, exc.value.column) == (1, 1)


def test_undeclared_variable_in_expression_is_rejected():
    with pytest.raises(CompileError, match="не объявлена"):
        compile_expression("x + 1")


@pytest.mark.parametrize(
    "source",
    [
        "int x = 1; int x = 2;",
        "int x; int x;",
        "int x = 1; int y = 2; int x = 3;",
    ],
)
def test_duplicate_declaration_is_rejected(source):
    with pytest.raises(CompileError, match="уже объявлена"):
        compile_program(source)


def test_declaration_inside_loop_is_rejected():
    with pytest.raises(CompileError, match="внутри тела цикла"):
        compile_program("int c = 1; while c { int x; }")


def test_declaration_inside_nested_block_in_loop_is_rejected():
    with pytest.raises(CompileError, match="внутри тела цикла"):
        compile_program("int c = 1; while c { if c { int x; } }")


def test_declaration_inside_plain_block_is_allowed():
    variables: dict = {}
    execute(compile_program("{ int x = 1; }"), variables)
    assert variables == {"x": 1}


# --------------------------------------------------------------------------
# несовместимые типы
# --------------------------------------------------------------------------


def test_array_in_arithmetic_is_rejected():
    with pytest.raises(CompileError, match="не применима к массиву"):
        compile_program("int a[2]; int x; x = a + 1;")


def test_array_in_comparison_is_rejected():
    with pytest.raises(CompileError, match="не применима к массиву"):
        compile_program("int a[2]; int x; x = a < 1;")


def test_unary_minus_on_array_is_rejected():
    with pytest.raises(CompileError, match="Унарная операция"):
        compile_program("int a[2]; int x; x = -a;")


def test_factorial_of_array_is_rejected():
    with pytest.raises(CompileError, match="Факториал применим только к целым"):
        compile_program("int a[2]; int x; x = a!;")


def test_index_of_non_array_is_rejected():
    with pytest.raises(CompileError, match="Индексация возможна только для массива"):
        compile_program("int x = 1; int y; y = x[0];")


def test_non_int_index_is_rejected():
    with pytest.raises(CompileError, match="Индекс массива должен иметь тип int"):
        compile_program("int a[2]; int b[2]; a[b] = 1;")


def test_nested_indexing_is_rejected():
    with pytest.raises(CompileError, match="Индексация возможна только для массива"):
        compile_program("int a[2]; int x; x = a[0][0];")


def test_array_element_value_must_be_int():
    with pytest.raises(CompileError, match="Значение элемента массива"):
        compile_program("int a[2]; int b[2]; a[0] = b;")


def test_assignment_type_mismatch_is_rejected():
    with pytest.raises(CompileError, match=r"Нельзя присвоить значение типа int\[\]"):
        compile_program("int x = 1; int a[2]; x = a;")


def test_condition_must_be_int():
    with pytest.raises(CompileError, match="Условие должно иметь тип int"):
        compile_program("int a[2]; if a { }")
    with pytest.raises(CompileError, match="Условие должно иметь тип int"):
        compile_program("int a[2]; while a { }")


def test_array_size_must_be_int():
    with pytest.raises(CompileError, match="Размер массива должен иметь тип int"):
        compile_program("int b[1]; int a[b];")


def test_array_literal_elements_must_be_int():
    with pytest.raises(CompileError, match="Элемент массива должен иметь тип int"):
        compile_program("int a[1]; int b = [a];")


# --------------------------------------------------------------------------
# вызовы встроенных функций
# --------------------------------------------------------------------------


def test_resize_rejects_non_array_first_argument():
    with pytest.raises(CompileError, match="Аргумент 1 функции 'resize'"):
        compile_program("int x = 1; resize(x, 2);")


def test_resize_rejects_wrong_argument_count():
    with pytest.raises(CompileError, match="ожидает 2 аргумента"):
        compile_program("int a[2]; resize(a);")


def test_abs_rejects_wrong_argument_count():
    with pytest.raises(CompileError, match="ожидает 1 аргумент"):
        compile_program("int x = abs(1, 2);")


def test_abs_rejects_array_argument():
    with pytest.raises(CompileError, match="Аргумент 1 функции 'abs'"):
        compile_program("int a[2]; int x = abs(a);")


def test_min_accepts_several_arguments():
    assert execute(compile_expression("min(2, 3, 4)")) == 2


def test_min_rejects_array_argument():
    # Массив не итерируем, поэтому min(array) не поддерживается.
    with pytest.raises(CompileError, match="Аргумент 1 функции 'min'"):
        compile_expression("min(a)", declared=(("a", Type.INT_ARRAY),))


def test_unknown_function_is_allowed_at_compile_time():
    # Такие функции подставляют при запуске: Machine(code, functions=...).
    code = compile_expression("twice(21)")
    assert execute(code, {}, {"twice": lambda v: 2 * v}) == 42


def test_unknown_function_is_still_a_runtime_error():
    with pytest.raises(CompileRuntimeError, match="не найдена"):
        execute(compile_expression("f()"))


# --------------------------------------------------------------------------
# внешние переменные
# --------------------------------------------------------------------------


def test_declared_external_variable_is_known():
    assert execute(compile_expression("x + 1", declared=("x",)), {"x": 41}) == 42


def test_declared_external_variable_keeps_bytecode():
    assert compile_expression("x + y * 2", declared=("x", "y")) == [
        ("LOAD", "x"), ("LOAD", "y"), ("PUSH", 2), ("MUL",), ("ADD",),
    ]


def test_declared_external_array_is_known():
    code = compile_expression("a[0]", declared=(("a", Type.INT_ARRAY),))
    assert code == [("LOAD", "a"), ("PUSH", 0), ("INDEX",)]


def test_compiled_code_carries_declared_types():
    code = compile_program("int x = 1; int a = [1, 2];")
    assert code.types == {"x": "int", "a": "int[]"}


def test_normalize_declared_accepts_names_and_pairs():
    assert normalize_declared(["x"]) == {"x": Type.INT}
    assert normalize_declared([("a", Type.INT_ARRAY)]) == {"a": Type.INT_ARRAY}


# --------------------------------------------------------------------------
# таблица символов
# --------------------------------------------------------------------------


def test_symbol_table_records_declared_types():
    compiler = Compiler("int x = 1; int a = [1, 2];")
    compiler.program()
    assert compiler.symbols.lookup("x").type is Type.INT
    assert compiler.symbols.lookup("a").type is Type.INT_ARRAY
    assert compiler.symbols.lookup("nope") is None


def test_symbol_table_knows_external_variables():
    table = SymbolTable(["x"])
    assert "x" in table
    assert table.lookup("x").type is Type.INT
    assert table.lookup("x").position == -1


def test_declaration_bytecode_is_unchanged():
    assert compile_program("int x = 1;") == [("PUSH", 1), ("DECL", "x")]
    assert compile_program("int x;") == [("PUSH", 0), ("DECL", "x")]
    assert compile_program("int a[3];") == [
        ("PUSH", 3), ("NEWARR", "int"), ("DECL", "a"),
    ]
    assert compile_program("int a = [1, 2];") == [
        ("PUSH", 1), ("PUSH", 2), ("MKARR", 2), ("DECL", "a"),
    ]
    assert compile_program("int a[2]; a[0] = 7;") == [
        ("PUSH", 2), ("NEWARR", "int"), ("DECL", "a"),
        ("LOAD", "a"), ("PUSH", 0), ("PUSH", 7), ("SETIDX",),
    ]


# --------------------------------------------------------------------------
# рантайм-проверки сохранены
# --------------------------------------------------------------------------


def test_runtime_guards_still_work_on_hand_written_bytecode():
    with pytest.raises(CompileRuntimeError, match="не объявлена"):
        execute([("LOAD", "x")])
    with pytest.raises(CompileRuntimeError, match="не применима к массиву"):
        execute([("PUSH", 2), ("NEWARR",), ("PUSH", 1), ("ADD",)])
    with pytest.raises(CompileRuntimeError, match="ожидался массив"):
        execute([("PUSH", 1), ("PUSH", 2), ("CALL", "resize", 2)])


def test_min_requires_at_least_one_argument():
    with pytest.raises(CompileError, match="ожидает не менее 1 аргумента"):
        compile_expression("min()")


def test_initializer_must_be_int():
    with pytest.raises(CompileError, match="Инициализатор переменной 'x'"):
        compile_program("int a[1]; int x = a;")


def test_second_array_literal_element_must_be_int():
    with pytest.raises(CompileError, match="Элемент массива должен иметь тип int"):
        compile_program("int a[1]; int b = [1, a];")


def test_element_assignment_to_undeclared_array_is_rejected():
    with pytest.raises(CompileError, match="не объявлена"):
        compile_program("b[0] = 1;")


def test_element_assignment_to_non_array_is_rejected():
    with pytest.raises(CompileError, match="Индексация возможна только для массива"):
        compile_program("int x = 1; x[0] = 1;")


def test_reading_array_element_as_statement_is_allowed():
    variables: dict = {}
    execute(compile_program("int a[2]; a[0];"), variables)
    assert variables["a"].items == [0, 0]


def test_symbol_table_as_types_and_len():
    table = SymbolTable(["x"])
    table.declare("a", Type.INT_ARRAY, 0)
    assert table.as_types() == {"x": Type.INT, "a": Type.INT_ARRAY}
    assert len(table) == 2


def test_plural_args():
    from stack_compiler import _plural_args

    assert _plural_args(1) == "аргумент"
    assert _plural_args(2) == "аргумента"
    assert _plural_args(5) == "аргументов"


# --------------------------------------------------------------------------
# литералы
# --------------------------------------------------------------------------


def test_int_literal():
    assert compile_expression("42") == [("PUSH", 42)]


def test_decimal_literal_is_double():
    assert compile_expression("1.5") == [("PUSH", 1.5)]


def test_float_literal_suffix():
    assert compile_expression("1.5f") == [("PUSH", 1.5)]


def test_double_literal_suffix():
    assert compile_expression("1.5d") == [("PUSH", 1.5)]


def test_exponent_literal_is_double():
    assert compile_expression("1e3") == [("PUSH", 1000.0)]
    assert compile_expression("1.5e-1") == [("PUSH", 0.15)]


def test_string_literal():
    assert compile_expression('"abc"') == [("PUSH", "abc")]


def test_single_quoted_string_literal():
    assert compile_expression("'abc'") == [("PUSH", "abc")]


def test_string_escapes():
    assert compile_expression(r'"a\nb"') == [("PUSH", "a\nb")]
    assert compile_expression(r'"a\tb"') == [("PUSH", "a\tb")]
    assert compile_expression(r'"a\\b"') == [("PUSH", "a\\b")]


def test_unterminated_string_is_compile_error():
    with pytest.raises(CompileError, match="Незакрытая строковая константа"):
        compile_expression('"abc')


def test_unknown_escape_is_compile_error():
    with pytest.raises(CompileError, match="управляющая последовательность"):
        compile_expression(r'"a\qb"')


# --------------------------------------------------------------------------
# объявления типов
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword, expected",
    [
        ("int", "int"),
        ("float", "float"),
        ("double", "double"),
        ("string", "string"),
    ],
)
def test_declaration_types(keyword, expected):
    compiler = Compiler(f"{keyword} x;")
    compiler.program()
    assert compiler.symbols.lookup("x").type.value == expected


def test_typed_array_declaration():
    compiler = Compiler("float a[2];")
    compiler.program()
    assert compiler.symbols.lookup("a").type.value == "float[]"


def test_string_array_declaration():
    compiler = Compiler("string s[2];")
    compiler.program()
    assert compiler.symbols.lookup("s").type.value == "string[]"


def test_type_keyword_call_is_not_a_declaration():
    # int(3) — вызов преобразования, а не объявление.
    assert compile_expression("int(3)") == [("PUSH", 3), ("CONVERT", "int")]


def test_array_is_filled_with_the_right_default():
    variables: dict = {}
    execute(compile_program("float a[2];"), variables)
    assert variables["a"].items == [0.0, 0.0]
    variables = {}
    execute(compile_program("string s[2];"), variables)
    assert variables["s"].items == ["", ""]


# --------------------------------------------------------------------------
# неявные преобразования и сужение
# --------------------------------------------------------------------------


def test_int_is_widened_to_float():
    code = compile_program("float x = 3;")
    assert code == [("PUSH", 3), ("CONVERT", "float"), ("DECL", "x")]


def test_int_is_widened_to_double():
    code = compile_program("double x = 3;")
    assert code == [("PUSH", 3), ("CONVERT", "double"), ("DECL", "x")]


def test_float_is_widened_to_double():
    code = compile_program("double x = 1.5f;")
    assert code == [("PUSH", 1.5), ("CONVERT", "double"), ("DECL", "x")]


def test_narrowing_to_float_is_rejected():
    with pytest.raises(
        CompileError, match="должен иметь тип float, получено double"
    ):
        compile_program("float x = 1.5;")


def test_narrowing_to_int_is_rejected():
    with pytest.raises(
        CompileError, match="должен иметь тип int, получено double"
    ):
        compile_program("int x = 1.5;")


def test_number_cannot_be_assigned_to_string():
    with pytest.raises(
        CompileError, match="должен иметь тип string, получено int"
    ):
        compile_program("string s = 5;")


def test_string_cannot_be_assigned_to_number():
    with pytest.raises(
        CompileError, match="должен иметь тип int, получено string"
    ):
        compile_program('int x = "abc";')


def test_narrowing_in_assignment_is_rejected():
    with pytest.raises(
        CompileError, match="Нельзя присвоить значение типа double"
    ):
        compile_program("float f = 1.5f; double d = 1.5; f = d;")


# --------------------------------------------------------------------------
# арифметика
# --------------------------------------------------------------------------


def test_int_arithmetic_stays_int():
    assert execute(compile_expression("7 / 2")) == 3


def test_double_arithmetic_is_real():
    assert execute(compile_expression("7.0 / 2.0")) == 3.5


def test_int_divided_by_double_is_real():
    assert execute(compile_expression("7 / 2.0")) == 3.5


def test_promotion_to_double():
    assert execute(compile_expression("1 + 2.5")) == 3.5


def test_promotion_to_float():
    assert execute(compile_expression("1 + 2.5f")) == 3.5


def test_float_and_double_promote_to_double():
    assert execute(compile_expression("2.5f + 3.5")) == 6.0


def test_modulo_requires_integers():
    with pytest.raises(CompileError, match="только к целым числам"):
        compile_expression("5.0 % 2")


def test_power_of_reals():
    assert execute(compile_expression("2.0 ^ 0.5")) == 2**0.5


def test_string_concatenation():
    assert execute(compile_expression('"a" + "b"')) == "ab"


def test_string_plus_number_is_rejected():
    with pytest.raises(CompileError, match="не применима к строке"):
        compile_expression('"a" + 1')


def test_number_plus_string_is_rejected():
    with pytest.raises(CompileError, match="не применима к строке"):
        compile_expression('1 + "a"')


def test_string_comparison_is_lexicographic():
    assert execute(compile_expression('"a" < "b"')) == 1
    assert execute(compile_expression('"b" < "a"')) == 0
    assert execute(compile_expression('"a" == "a"')) == 1


def test_string_subtraction_is_rejected():
    with pytest.raises(CompileError, match="не применима к строке"):
        compile_expression('"a" - "b"')


def test_unary_minus_keeps_the_type():
    assert execute(compile_expression("-1.5")) == -1.5
    assert execute(compile_expression("-1")) == -1


def test_logical_not_gives_int():
    assert execute(compile_expression("!0")) == 1
    assert execute(compile_expression("!1.5")) == 0


def test_factorial_requires_int():
    with pytest.raises(CompileError, match="только к целым"):
        compile_expression("2.5!")


# --------------------------------------------------------------------------
# функции-преобразования
# --------------------------------------------------------------------------


def test_int_conversion_truncates():
    assert execute(compile_expression("int(3.9)")) == 3


def test_int_conversion_parses_string():
    assert execute(compile_expression('int("42")')) == 42


def test_int_conversion_of_bad_string_is_runtime_error():
    with pytest.raises(CompileRuntimeError, match="Не удалось преобразовать"):
        execute(compile_expression('int("abc")'))


def test_float_and_double_conversion():
    assert execute(compile_expression("float(3)")) == 3.0
    assert execute(compile_expression("double(3)")) == 3.0
    assert execute(compile_expression("float(1.5)")) == 1.5


def test_string_conversion():
    assert execute(compile_expression("string(42)")) == "42"
    assert execute(compile_expression("string(1.5)")) == "1.5"
    assert execute(compile_expression('string("a")')) == "a"


def test_conversion_requires_one_argument():
    with pytest.raises(CompileError, match="ожидает 1 аргумент"):
        compile_expression("int(1, 2)")


# --------------------------------------------------------------------------
# встроенные функции с новыми типами
# --------------------------------------------------------------------------


def test_abs_keeps_the_type():
    assert execute(compile_expression("abs(-3)")) == 3
    assert execute(compile_expression("abs(-1.5)")) == 1.5


def test_sqrt_returns_float():
    assert execute(compile_expression("sqrt(16)")) == 4.0


def test_min_max_promote():
    assert execute(compile_expression("min(1, 2.5)")) == 1
    assert execute(compile_expression("max(1, 2.5)")) == 2.5


def test_builtin_rejects_string_argument():
    with pytest.raises(CompileError, match="должен иметь числовой тип"):
        compile_expression('abs("a")')
