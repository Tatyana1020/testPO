"""Тесты для stack_compiler.py — однопроходный компилятор выражений и операторов.

Проверяются: точность кода стековой машины (приоритеты, ассоциативность),
выполнение выражений и программ, операторы if/else if/else и while,
переходы, ошибки компиляции и времени выполнения, внутренние переходы
Compiler по символам и командный интерфейс.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from stack_compiler import (
    BUILTIN_FUNCTIONS,
    BINARY_OPS,
    COMPARISON_OPS,
    Compiler,
    CompileError,
    CompileRuntimeError,
    KEYWORDS,
    LOGICAL_OPS,
    OPCODES,
    PREFIX_OPS,
    SUM_OPS,
    TERM_OPS,
    _apply,
    _div,
    _fact,
    _looks_like_program,
    _pop,
    compile_expression,
    compile_program,
    disassemble,
    execute,
    main,
)

OPERAND_ERROR = "Ожидался операнд"
EXTRA_CHAR_ERROR = "Лишний символ"
SEMICOLON_ERROR = "Ожидалось ';'"


def make_compiler(source):
    return Compiler(source)


def run_program(source, variables=None):
    variables = {} if variables is None else dict(variables)
    result = execute(compile_program(source), variables)
    return result, variables


# --------------------------------------------------------------------------
# константы модуля
# --------------------------------------------------------------------------


def test_operator_groups_are_tuples_of_strings():
    for group in (LOGICAL_OPS, COMPARISON_OPS, SUM_OPS, TERM_OPS, PREFIX_OPS,
                  KEYWORDS):
        assert isinstance(group, tuple)
        assert all(isinstance(op, str) for op in group)


def test_operator_groups_content():
    assert LOGICAL_OPS == ("&&", "||")
    assert SUM_OPS == ("+", "-")
    assert TERM_OPS == ("*", "/", "%")
    assert PREFIX_OPS == ("+", "-", "!")
    assert KEYWORDS == ("if", "else", "while")


def test_comparison_ops_contain_both_spellings_of_inequality():
    assert "<>" in COMPARISON_OPS
    assert "!=" in COMPARISON_OPS


def test_every_two_char_op_precedes_its_one_char_prefix():
    for op in COMPARISON_OPS + LOGICAL_OPS:
        for shorter in (op[:1], op[:2]):
            if shorter in COMPARISON_OPS and shorter != op:
                assert COMPARISON_OPS.index(shorter) > COMPARISON_OPS.index(op)


def test_opcodes_cover_every_operator():
    for op in LOGICAL_OPS + COMPARISON_OPS:
        assert op in OPCODES


def test_opcodes_map_operators_to_expected_instructions():
    assert OPCODES["&&"] == "AND"
    assert OPCODES["||"] == "OR"
    assert OPCODES["<"] == "LT"
    assert OPCODES[">"] == "GT"
    assert OPCODES["=="] == "EQ"
    assert OPCODES["!="] == OPCODES["<>"] == "NE"
    assert OPCODES["<="] == "LE"
    assert OPCODES[">="] == "GE"


def test_binary_ops_table_matches_opcodes_values():
    assert set(BINARY_OPS) == {
        "ADD", "SUB", "MUL", "DIV", "MOD", "POW", "AND", "OR",
        "LT", "GT", "EQ", "NE", "LE", "GE",
    }
    assert set(OPCODES.values()) <= set(BINARY_OPS)


def test_builtin_functions_are_available():
    assert set(BUILTIN_FUNCTIONS) == {"abs", "min", "max", "sqrt"}


# --------------------------------------------------------------------------
# код выражений: приоритеты и ассоциативность
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        ("1 + 2 * 3", [("PUSH", 1), ("PUSH", 2), ("PUSH", 3), ("MUL",), ("ADD",)]),
        ("1 * 2 + 3", [("PUSH", 1), ("PUSH", 2), ("MUL",), ("PUSH", 3), ("ADD",)]),
        ("1 - 2 - 3", [("PUSH", 1), ("PUSH", 2), ("SUB",), ("PUSH", 3), ("SUB",)]),
        ("8 / 4 / 2", [("PUSH", 8), ("PUSH", 4), ("DIV",), ("PUSH", 2), ("DIV",)]),
        ("2 ^ 3 * 4", [("PUSH", 2), ("PUSH", 3), ("POW",), ("PUSH", 4), ("MUL",)]),
        ("2 * 3 ^ 4", [("PUSH", 2), ("PUSH", 3), ("PUSH", 4), ("POW",), ("MUL",)]),
        (
            "1 + 2 < 3 && 4",
            [("PUSH", 1), ("PUSH", 2), ("ADD",), ("PUSH", 3), ("LT",),
             ("PUSH", 4), ("AND",)],
        ),
        (
            "a - b - c",
            [("LOAD", "a"), ("LOAD", "b"), ("SUB",), ("LOAD", "c"), ("SUB",)],
        ),
        ("(1 + 2) * 3", [("PUSH", 1), ("PUSH", 2), ("ADD",), ("PUSH", 3), ("MUL",)]),
    ],
)
def test_compile_expression_generates_expected_code(source, expected):
    assert compile_expression(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("x", [("LOAD", "x")]),
        ("x!", [("LOAD", "x"), ("FACT",)]),
        ("x!!", [("LOAD", "x"), ("FACT",), ("FACT",)]),
        ("-x", [("LOAD", "x"), ("NEG",)]),
        ("+x", [("LOAD", "x")]),
        ("!x", [("LOAD", "x"), ("NOT",)]),
        ("!!x", [("LOAD", "x"), ("NOT",), ("NOT",)]),
        ("-!x", [("LOAD", "x"), ("NOT",), ("NEG",)]),
        ("-x!", [("LOAD", "x"), ("FACT",), ("NEG",)]),
        ("!x!", [("LOAD", "x"), ("FACT",), ("NOT",)]),
        ("007", [("PUSH", 7)]),
        ("f()", [("CALL", "f", 0)]),
        ("f(1)", [("PUSH", 1), ("CALL", "f", 1)]),
        ("f(1, 2)", [("PUSH", 1), ("PUSH", 2), ("CALL", "f", 2)]),
        ("f(g(1) + 2)", [("PUSH", 1), ("CALL", "g", 1), ("PUSH", 2), ("ADD",),
                         ("CALL", "f", 1)]),
        ("1 !== 2", [("PUSH", 1), ("FACT",), ("PUSH", 2), ("EQ",)]),
    ],
)
def test_compile_expression_operands_and_calls(source, expected):
    assert compile_expression(source) == expected


def test_double_bang_equal_is_factorial_then_equality():
    assert compile_expression("1 !== 2") == [
        ("PUSH", 1), ("FACT",), ("PUSH", 2), ("EQ",)
    ]


def test_bang_equal_is_inequality_not_factorial():
    assert compile_expression("1 != 2") == [("PUSH", 1), ("PUSH", 2), ("NE",)]


# --------------------------------------------------------------------------
# выполнение выражений
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        ("1", 1),
        ("007", 7),
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("8 - 3 - 2", 3),
        ("10 / 4", 2),
        ("7 / 2", 3),
        ("-7 / 2", -3),
        ("7 / -2", -3),
        ("-7 / -2", 3),
        ("2 ^ 10", 1024),
        ("2 ^ 3! * 4", 256),
        ("5!", 120),
        ("0!", 1),
        ("-3!", -6),
        ("1 + 2 < 4", 1),
        ("1 + 2 < 3", 0),
        ("4 >= 4", 1),
        ("4 <= 3", 0),
        ("1 == 1", 1),
        ("1 == 2", 0),
        ("1 <> 2", 1),
        ("1 != 1", 0),
        ("1 && 0", 0),
        ("1 || 0", 1),
        ("1 && 2", 1),
        ("!(1 == 1)", 0),
        ("max(1, 7) + 1", 8),
        ("abs(-3)", 3),
        ("min(2, 3) ^ 2", 4),
        ("sqrt(16)", 4),
        ("!(2 != 2) && max(1, 2) + 3!", 1),
        ("100000000000000000000 + 1", 100000000000000000001),
    ],
)
def test_execute_expression_result(source, expected):
    assert execute(compile_expression(source)) == expected


def test_execute_expression_uses_variables():
    code = compile_expression("x + y * 2")
    assert execute(code, {"x": 1, "y": 10}) == 21


def test_execute_expression_uses_custom_functions():
    assert execute(compile_expression("double(21)"), {}, {"double": lambda v: 2 * v}) == 42


def test_custom_function_overrides_builtin():
    assert execute(compile_expression("abs(-3)"), {}, {"abs": lambda v: 999}) == 999


def test_execute_returns_none_for_empty_code():
    assert execute([]) is None


def test_execute_mutates_given_variables_dictionary():
    variables = {}
    execute([("PUSH", 5), ("STORE", "x")], variables)
    assert variables == {"x": 5}


# --------------------------------------------------------------------------
# операторы: if / else if / else
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, initial, expected",
    [
        ("if 1 { x = 5; }", {}, {"x": 5}),
        ("if 0 { x = 5; }", {}, {}),
        ("if 0 { x = 5; } else { x = 9; }", {}, {"x": 9}),
        ("if 1 { x = 5; } else { x = 9; }", {}, {"x": 5}),
        ("if 0 { x = 1; } else if 1 { x = 2; }", {}, {"x": 2}),
        ("if 0 { x = 1; } else if 0 { x = 2; } else { x = 3; }", {}, {"x": 3}),
        (
            "if 1 { x = 1; } else if 0 { x = 2; } else { x = 3; }",
            {},
            {"x": 1},
        ),
        (
            "if 0 { x = 1; } else if 0 { x = 2; } else if 1 { x = 3; } else { x = 4; }",
            {},
            {"x": 3},
        ),
        ("if 1 { }", {}, {}),
        ("x = 1; if x { y = 10; } else { y = 20; }", {"x": 1}, {"x": 1, "y": 10}),
        ("x = 0; if x { y = 10; } else { y = 20; }", {"x": 0}, {"x": 0, "y": 20}),
        ("if 1 { if 0 { x = 1; } else { x = 2; } }", {}, {"x": 2}),
        ("x = 3; if x > 1 { if x > 2 { y = 1; } }", {}, {"x": 3, "y": 1}),
        ("if 1! { x = 7; }", {}, {"x": 7}),
    ],
)
def test_execute_if_statements(source, initial, expected):
    result, variables = run_program(source, initial)
    assert result is None
    assert variables == expected


def test_compile_if_generates_expected_code():
    assert compile_program("if 1 { x = 5; }") == [
        ("PUSH", 1), ("JZ", 5), ("PUSH", 5), ("STORE", "x"), ("JMP", 5),
    ]


def test_compile_if_else_generates_expected_code():
    assert compile_program("if 1 { x = 5; } else { x = 9; }") == [
        ("PUSH", 1), ("JZ", 5), ("PUSH", 5), ("STORE", "x"), ("JMP", 7),
        ("PUSH", 9), ("STORE", "x"),
    ]


def test_compile_else_if_chain_generates_expected_code():
    code = compile_program("if 0 { x = 1; } else if 0 { x = 2; } else { x = 3; }")
    assert code == [
        ("PUSH", 0), ("JZ", 5), ("PUSH", 1), ("STORE", "x"), ("JMP", 12),
        ("PUSH", 0), ("JZ", 10), ("PUSH", 2), ("STORE", "x"), ("JMP", 12),
        ("PUSH", 3), ("STORE", "x"),
    ]


# --------------------------------------------------------------------------
# оператор while
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, initial, expected",
    [
        ("while 0 { }", {}, {}),
        ("i = 0; while i < 5 { i = i + 1; }", {}, {"i": 5}),
        ("i = 0; s = 0; while i < 4 { i = i + 1; s = s + i; }", {}, {"i": 4, "s": 10}),
        ("i = 3; while i { i = i - 1; }", {}, {"i": 0}),
        ("x = 5; if x > 3 { while x > 3 { x = x - 1; } } else { x = 0; }", {},
         {"x": 3}),
        ("i = 0; while i < 3 { j = 0; while j < 2 { j = j + 1; } i = i + 1; }", {},
         {"i": 3, "j": 2}),
    ],
)
def test_execute_while_statements(source, initial, expected):
    result, variables = run_program(source, initial)
    assert result is None
    assert variables == expected


def test_compile_while_generates_expected_code():
    assert compile_program("while i < 3 { i = i + 1; }") == [
        ("LOAD", "i"), ("PUSH", 3), ("LT",), ("JZ", 9),
        ("LOAD", "i"), ("PUSH", 1), ("ADD",), ("STORE", "i"),
        ("JMP", 0),
    ]


# --------------------------------------------------------------------------
# блоки, присваивание, оператор-выражение
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, initial, expected",
    [
        ("x = 1;", {}, {"x": 1}),
        ("x = 1", {}, {"x": 1}),
        ("x = 1 + 2 * 3;", {}, {"x": 7}),
        ("x = 1; x = x + 1;", {}, {"x": 2}),
        ("x = 1; x == 1;", {"x": 1}, {"x": 1}),
        ("1 + 2;", {}, {}),
        (";", {}, {}),
        ("{ a = 1; } b = a + 1;", {}, {"a": 1, "b": 2}),
        ("{ { x = 1; } }", {}, {"x": 1}),
        ("ifx = 1; whilex = 2; elsewhere = 3;", {},
         {"ifx": 1, "whilex": 2, "elsewhere": 3}),
        ("x_1 = 1; _y = 2;", {}, {"x_1": 1, "_y": 2}),
    ],
)
def test_execute_simple_statements(source, initial, expected):
    result, variables = run_program(source, initial)
    assert result is None
    assert variables == expected


def test_compile_expression_statement_pops_value():
    assert compile_program("1 + 2;") == [
        ("PUSH", 1), ("PUSH", 2), ("ADD",), ("POP",),
    ]


def test_compile_assignment_stores_value():
    assert compile_program("x = 1 + 2;") == [
        ("PUSH", 1), ("PUSH", 2), ("ADD",), ("STORE", "x"),
    ]


# --------------------------------------------------------------------------
# переходы: патчинг адресов
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "if 1 { }",
        "if 0 { } else { }",
        "if 0 { } else if 1 { } else if 0 { } else { }",
        "while 0 { }",
        "i = 0; while i < 2 { if i { x = 1; } else { x = 2; } i = i + 1; }",
    ],
)
def test_all_jump_targets_are_patched(source):
    code = compile_program(source)
    jumps = [i for i in code if i[0] in ("JZ", "JMP")]
    assert jumps
    for _, target in jumps:
        assert target != -1
        assert 0 <= target <= len(code)


# --------------------------------------------------------------------------
# ошибки компиляции
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, fragment",
    [
        ("", OPERAND_ERROR),
        ("1 +", OPERAND_ERROR),
        ("*", OPERAND_ERROR),
        ("(1 + 2", "Ожидалось ')'"),
        ("f(1,", OPERAND_ERROR),
        ("f(1 2)", "Ожидалось ')'"),
        ("= 1", OPERAND_ERROR),
        ("1 2", EXTRA_CHAR_ERROR),
        ("1 $ 2", EXTRA_CHAR_ERROR),
        ("1 ^ 2 ^ 3", EXTRA_CHAR_ERROR),
    ],
)
def test_compile_expression_rejects_invalid_source(source, fragment):
    with pytest.raises(CompileError) as exc:
        compile_expression(source)
    assert fragment in exc.value.message


@pytest.mark.parametrize(
    "source, fragment",
    [
        ("if", OPERAND_ERROR),
        ("if 1 x = 1;", "Ожидалось '{'"),
        ("if 1 { x = 1 }", SEMICOLON_ERROR),
        ("if 1 { } else { } else { }", SEMICOLON_ERROR),
        ("while", OPERAND_ERROR),
        ("while { }", OPERAND_ERROR),
        ("while 1 {", "Ожидалось '}'"),
        ("x = ", OPERAND_ERROR),
        ("1 = 2;", SEMICOLON_ERROR),
    ],
)
def test_compile_program_rejects_invalid_source(source, fragment):
    with pytest.raises(CompileError) as exc:
        compile_program(source)
    assert fragment in exc.value.message


@pytest.mark.parametrize(
    "source, line, column",
    [
        ("1 +", 1, 4),
        ("1 2", 1, 3),
        ("if 1 x = 1;", 1, 6),
        ("if 1 { x = 1 }", 1, 14),
        ("x =\n  * 1;", 2, 3),
        ("if 0 { } else\n{ 1 2; }", 2, 5),
    ],
)
def test_compile_error_position(source, line, column):
    with pytest.raises(CompileError) as exc:
        compile_program(source) if _looks_like_program(source) else compile_expression(
            source
        )
    assert (exc.value.line, exc.value.column) == (line, column)


def test_compile_error_str_contains_position_and_caret():
    with pytest.raises(CompileError) as exc:
        compile_expression("1 $ 2")
    assert "позиция: строка 1, столбец 3" in str(exc.value)
    assert str(exc.value).splitlines()[0] == "Лишний символ '$' после выражения"
    assert str(exc.value).endswith("  1 $ 2\n    ^")


def test_compile_error_at_position_zero():
    with pytest.raises(CompileError) as exc:
        compile_expression("=")
    assert (exc.value.line, exc.value.column) == (1, 1)


# --------------------------------------------------------------------------
# ошибки времени выполнения
# --------------------------------------------------------------------------


def test_execute_division_by_zero():
    with pytest.raises(CompileRuntimeError, match="Деление на ноль"):
        execute(compile_expression("1 / 0"))


def test_execute_factorial_of_negative():
    with pytest.raises(CompileRuntimeError, match="Факториал отрицательного числа"):
        execute(compile_expression("(-3)!"))


def test_execute_negative_power():
    with pytest.raises(CompileRuntimeError, match="Отрицательная степень"):
        execute(compile_expression("2 ^ -1"))


def test_execute_undeclared_variable():
    with pytest.raises(CompileRuntimeError, match="не объявлена"):
        execute(compile_expression("zz"))


def test_execute_unknown_function():
    with pytest.raises(CompileRuntimeError, match="не найдена"):
        execute(compile_expression("f()"))


def test_execute_unknown_instruction():
    with pytest.raises(CompileRuntimeError, match="Неизвестная инструкция"):
        execute([("WHAT",)])


def test_execute_stack_with_several_values_is_error():
    with pytest.raises(CompileRuntimeError, match="стек содержит 2"):
        execute([("PUSH", 1), ("PUSH", 2)])


def test_execute_pop_from_empty_stack():
    with pytest.raises(CompileRuntimeError, match="Стек пуст"):
        execute([("POP",)])


def test_execute_stops_infinite_loop_by_step_limit():
    with pytest.raises(CompileRuntimeError, match="бесконечный цикл"):
        execute(compile_program("while 1 { }"), {}, max_steps=500)


# --------------------------------------------------------------------------
# внутренние переходы Compiler
# --------------------------------------------------------------------------


def test_compiler_peek_and_skip():
    compiler = make_compiler("  a + b")
    assert compiler._peek() == " "
    compiler._skip()
    assert compiler._peek() == "a"
    assert compiler._peek(2) == "+"
    assert compiler._peek(100) == ""


def test_compiler_at_end_and_here():
    compiler = make_compiler("a")
    assert compiler._at_end() is False
    assert compiler._here() == "'a'"
    compiler._i = 1
    assert compiler._at_end() is True
    assert compiler._here() == "конец строки"


def test_compiler_match_op_prefers_longest():
    compiler = make_compiler("<= x")
    assert compiler._match_op(COMPARISON_OPS) == "<="
    assert compiler._i == 2


def test_compiler_match_op_returns_empty_string():
    assert make_compiler("x")._match_op(SUM_OPS) == ""


def test_compiler_match_kw_respects_word_boundary():
    assert make_compiler("if 1")._match_kw("if") is True
    assert make_compiler("ifx")._match_kw("if") is False
    assert make_compiler("elsewhere")._match_kw("else") is False
    assert make_compiler("while_1")._match_kw("while") is False


def test_compiler_match_kw_matches_at_end_of_source():
    compiler = make_compiler("while")
    assert compiler._match_kw("while") is True
    assert compiler._at_end() is True


def test_compiler_emit_jump_and_patch():
    compiler = make_compiler("1")
    index = compiler._emit_jump("JZ")
    assert compiler.code[index] == ("JZ", -1)
    compiler._patch(index, 42)
    assert compiler.code[index] == ("JZ", 42)


def test_compiler_patch_keeps_operation():
    compiler = make_compiler("1")
    index = compiler._emit_jump("JMP")
    compiler._patch(index, 7)
    assert compiler.code[index] == ("JMP", 7)


def test_compiler_starts_inequality():
    compiler = make_compiler("!= x")
    assert compiler._starts_inequality() is True
    compiler = make_compiler("!== x")
    assert compiler._starts_inequality() is False
    compiler = make_compiler("! x")
    assert compiler._starts_inequality() is False


@pytest.mark.parametrize(
    "source, expected",
    [("a", None), ("a = 1", "a"), ("= 1", None), ("== 1", None), ("1 + 2", None),
     ("", None)],
)
def test_compiler_try_assignment(source, expected):
    compiler = make_compiler(source)
    assert compiler._try_assignment() == expected
    if expected is None:
        assert compiler._i == 0


def test_compiler_try_assignment_returns_name_and_consumes_equals():
    compiler = make_compiler("x = 1")
    assert compiler._try_assignment() == "x"
    compiler._skip()
    assert compiler._peek() == "1"


@pytest.mark.parametrize(
    "source, expected",
    [("-a", ["-"]), ("!a", ["!"]), ("!!a", ["!", "!"]), ("+-a", ["+", "-"]),
     ("a", []), ("(a)", [])],
)
def test_compiler_collect_prefix(source, expected):
    assert make_compiler(source)._collect_prefix() == expected


def test_compiler_collect_prefix_stops_at_inequality():
    compiler = make_compiler("!= a")
    assert compiler._collect_prefix() == []
    assert compiler._i == 0


def test_compiler_ident_and_number():
    compiler = make_compiler("abc1")
    assert compiler._ident() == "abc1"
    compiler = make_compiler("42 rest")
    assert compiler._number() == 42
    assert compiler._peek() == " "


def test_compiler_take_char_raises_on_mismatch():
    compiler = make_compiler("a}")
    with pytest.raises(CompileError) as exc:
        compiler._take_char("{", "'{'")
    assert exc.value.message == "Ожидалось '{', получено 'a'"


# --------------------------------------------------------------------------
# вспомогательные функции
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "left, right, expected",
    [(7, 2, 3), (-7, 2, -3), (7, -2, -3), (-7, -2, 3), (0, 5, 0)],
)
def test_div_truncates_towards_zero(left, right, expected):
    assert _div(left, right) == expected


def test_div_by_zero_raises():
    with pytest.raises(CompileRuntimeError, match="Деление на ноль"):
        _div(1, 0)


@pytest.mark.parametrize("value, expected", [(0, 1), (1, 1), (5, 120), (10, 3628800)])
def test_fact_of_non_negative(value, expected):
    assert _fact(value) == expected


def test_fact_of_negative_raises():
    with pytest.raises(CompileRuntimeError, match="Факториал отрицательного"):
        _fact(-1)


def test_apply_uses_binary_ops_table():
    assert _apply("ADD", 2, 3) == 5
    assert _apply("LE", 2, 3) == 1
    assert _apply("POW", 2, 3) == 8


def test_apply_division_and_power_delegate_to_helpers():
    with pytest.raises(CompileRuntimeError, match="Деление на ноль"):
        _apply("DIV", 1, 0)
    with pytest.raises(CompileRuntimeError, match="Отрицательная степень"):
        _apply("POW", 2, -1)


def test_pop_returns_last_value():
    assert _pop([1, 2, 3], 0) == 3


def test_pop_on_empty_stack_mentions_pc():
    with pytest.raises(CompileRuntimeError, match="инструкции 4"):
        _pop([], 4)


def test_disassemble_formats_addresses_and_arguments():
    assert disassemble([("PUSH", 1), ("PUSH", 2), ("ADD",)]) == (
        "0000  PUSH  1\n0001  PUSH  2\n0002  ADD   "
    )


def test_disassemble_renders_call_with_name_and_argc():
    assert "0000  CALL  max 2" in disassemble([("CALL", "max", 2)])


def test_disassemble_of_empty_code_is_empty_string():
    assert disassemble([]) == ""


@pytest.mark.parametrize(
    "source, expected",
    [
        ("1 + 2", False),
        (" x + 1", False),
        ("if 1 {}", True),
        ("  while 1 {}", True),
        ("ifx", False),
        ("x = 1;", True),
        ("x = 1", True),
        ("a == b", False),
        ("{ }", True),
        ("if", True),
    ],
)
def test_looks_like_program(source, expected):
    assert _looks_like_program(source) is expected


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def test_main_without_arguments_prints_usage(capsys):
    assert main(["stack_compiler.py"]) == 2
    assert "Использование" in capsys.readouterr().out


def test_main_prints_disassembly_for_expression(capsys):
    assert main(["stack_compiler.py", "1 + 2"]) == 0
    out = capsys.readouterr().out
    assert "0000  PUSH  1" in out
    assert "Результат" not in out


def test_main_runs_expression_with_variables(capsys):
    assert main(["stack_compiler.py", "--run", "x=41", "x + 1"]) == 0
    out = capsys.readouterr().out
    assert "Результат: 42" in out
    assert "Переменные" not in out


def test_main_runs_program_and_prints_variables(capsys):
    assert main(["stack_compiler.py", "--run", "if 1 { x = 5; }"]) == 0
    out = capsys.readouterr().out
    assert "STORE x" in out
    assert "Переменные: x=5" in out


def test_main_prints_no_variables_for_program_without_changes(capsys):
    assert main(["stack_compiler.py", "--run", "while 0 { }"]) == 0
    assert "Переменные: нет" in capsys.readouterr().out


def test_main_reports_compile_error(capsys):
    assert main(["stack_compiler.py", "1 $ 2"]) == 1
    out = capsys.readouterr().out
    assert out.startswith("Ошибка компиляции: Лишний символ '$' после выражения")
    assert "позиция: строка 1, столбец 3" in out


def test_main_reports_runtime_error(capsys):
    assert main(["stack_compiler.py", "--run", "1 / 0"]) == 1
    assert "Ошибка выполнения: Деление на ноль" in capsys.readouterr().out


def test_main_stops_infinite_loop(capsys):
    assert main(["stack_compiler.py", "--run", "while 1 { }"]) == 1
    assert "бесконечный цикл" in capsys.readouterr().out


# --------------------------------------------------------------------------
# запуск модуля как скрипта
# --------------------------------------------------------------------------


MODULE_PATH = Path(__file__).with_name("stack_compiler.py")


def run_script(args=()):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=MODULE_PATH.parent,
    )


def test_script_prints_code_and_result_for_expression():
    result = run_script(["--run", "1 + 2 * 3"])
    assert result.returncode == 0
    assert result.stderr == ""
    assert "MUL" in result.stdout
    assert "Результат: 7" in result.stdout


def test_script_runs_program_and_shows_variables():
    result = run_script(["--run", "i = 0; while i < 3 { i = i + 1; }"])
    assert result.returncode == 0
    assert "JMP" in result.stdout
    assert "Переменные: i=3" in result.stdout


def test_script_exits_one_on_compile_error():
    result = run_script(["1 ^ 2 ^ 3"])
    assert result.returncode == 1
    assert "Ошибка компиляции" in result.stdout


def test_script_exits_one_on_runtime_error():
    result = run_script(["--run", "1 / 0"])
    assert result.returncode == 1
    assert "Ошибка выполнения: Деление на ноль" in result.stdout


def test_script_without_arguments_exits_with_two():
    result = run_script([])
    assert result.returncode == 2
    assert "Использование" in result.stdout