"""Тесты для syntax_check.py — синтаксическая проверка выражений.

Разбор выполняется напрямую по символам исходного текста, поэтому в тестах
нет ни токенов, ни лексического этапа: проверяются входные строки,
сообщения об ошибках и внутренние переходы Checker по символам.

    выражение := [+-] операнд { "!" } { бинарная операция ОПЕРАНД }
    операнд   := имя | константа | "(" выражение ")"
"""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

import syntax_check
from syntax_check import (
    BINARY_OPS,
    PREFIX_OPS,
    Checker,
    SyntaxErrorEx,
    check,
    main,
)

OPERAND_ERROR = "Ожидался операнд"
EXTRA_CHAR_ERROR = "Лишний символ"
EXPECTED_RPAREN = "Ожидалось ')'"


def make_checker(source):
    return Checker(source)


# --------------------------------------------------------------------------
# разбор без лексического этапа
# --------------------------------------------------------------------------


def test_module_has_no_tokenizer():
    assert not hasattr(syntax_check, "Token")
    assert not hasattr(syntax_check, "tokenize")


def test_checker_reads_source_characters_directly():
    checker = make_checker("a + b")
    assert checker._peek() == "a"
    assert checker._peek(2) == "+"
    assert checker._peek(4) == "b"


def test_checker_peek_returns_empty_string_past_end():
    checker = make_checker("a")
    assert checker._peek(1) == ""
    assert checker._peek(99) == ""


def test_checker_peek_looks_backwards_without_bounds_error():
    checker = make_checker("abc")
    checker._i = 2
    assert checker._peek(-1) == "b"
    assert checker._peek(-2) == "a"
    checker._i = 0
    assert checker._peek(-1) == ""


def test_checker_skip_spaces_moves_index():
    checker = make_checker(" \t\n ab")
    checker._skip_spaces()
    assert checker._peek() == "a"


@pytest.mark.parametrize("space", [" ", "\t", "\n", "\r\n", "\u00a0", "\u3000"])
def test_every_whitespace_kind_is_skipped(space):
    assert check(f"{space}a{space}+{space}b{space}") is None


def test_checker_at_end_is_false_in_middle_and_true_at_end():
    checker = make_checker("a + b")
    assert checker._at_end() is False
    checker._i = len(checker._source)
    assert checker._at_end() is True


def test_checker_at_end_skips_trailing_whitespace():
    checker = make_checker("a  \n ")
    checker._i = 1
    assert checker._at_end() is True


def test_checker_here_describes_character_or_end_of_source():
    checker = make_checker("a)")
    assert checker._here() == "'a'"
    checker._i = 1
    assert checker._here() == "')'"


def test_checker_here_reports_end_of_source():
    checker = make_checker("a")
    checker._i = 1
    assert checker._here() == "конец строки"


def test_checker_skip_spaces_stops_at_end_of_source():
    checker = make_checker("   ")
    checker._skip_spaces()
    assert checker._i == 3


# --------------------------------------------------------------------------
# _match_op, _match_prefix, _match_factorials
# --------------------------------------------------------------------------


def test_match_op_returns_operator_and_advances():
    checker = make_checker("+ b")
    assert checker._match_op(BINARY_OPS) == "+"
    assert checker._i == 1


def test_match_op_prefers_longest_match():
    checker = make_checker("<= b")
    assert checker._match_op(BINARY_OPS) == "<="
    assert checker._i == 2


def test_match_op_returns_empty_string_when_nothing_matches():
    checker = make_checker("b")
    assert checker._match_op(BINARY_OPS) == ""


def test_match_op_skips_spaces_before_matching():
    checker = make_checker("   *")
    assert checker._match_op(BINARY_OPS) == "*"


@pytest.mark.parametrize(
    "source, expected_index",
    [("-a", 1), ("+a", 1), ("!a", 1), ("!!a", 2), ("- - a", 4), ("! -a", 3)],
)
def test_match_prefix_consumes_all_leading_signs(source, expected_index):
    checker = make_checker(source)
    assert checker._match_prefix() is True
    assert checker._i == expected_index
    assert checker._peek() == "a"


@pytest.mark.parametrize("source", ["a", "(", "*", "=", "&", "1", "  a"])
def test_match_prefix_rejects_non_signs(source):
    assert make_checker(source)._match_prefix() is False


def test_match_prefix_without_signs_advances_nothing():
    checker = make_checker(" a")
    assert checker._match_prefix() is False
    assert checker._i == 1


def test_match_factorials_consumes_repeated_bangs():
    checker = make_checker("!!! + b")
    checker._match_factorials()
    assert checker._i == 4
    assert checker._peek() == "+"


def test_match_factorials_stops_at_bang_equal():
    checker = make_checker("!= b")
    checker._match_factorials()
    assert checker._i == 0
    assert checker._match_op(BINARY_OPS) == "!="


def test_match_factorials_consumes_bang_before_double_equal():
    checker = make_checker("!== b")
    checker._match_factorials()
    assert checker._i == 1
    assert checker._match_op(BINARY_OPS) == "=="


def test_match_factorials_keeps_space_separated_bangs():
    checker = make_checker("! ! + b")
    checker._match_factorials()
    assert checker._i == 4
    assert checker._peek() == "+"


# --------------------------------------------------------------------------
# _eat
# --------------------------------------------------------------------------


def test_eat_consumes_expected_character():
    checker = make_checker("(a)")
    checker._eat("(", "'('")
    assert checker._i == 1


def test_eat_raises_on_unexpected_character():
    checker = make_checker("a)")
    with pytest.raises(SyntaxErrorEx) as exc:
        checker._eat(")", "')'")
    assert exc.value.message == "Ожидалось ')', получено 'a'"
    assert exc.value.column == 1


def test_eat_raises_at_end_of_source():
    checker = make_checker("   ")
    with pytest.raises(SyntaxErrorEx) as exc:
        checker._eat(")", "')'")
    assert exc.value.message == "Ожидалось ')', получено конец строки"


def test_eat_skips_spaces_before_character():
    checker = make_checker("(a   )")
    checker._eat("(", "'('")
    checker.operand()
    checker._eat(")", "')'")
    assert checker._at_end() is True


# --------------------------------------------------------------------------
# operand
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["a", "name", "_", "_x9", "имя", "变量"])
def test_operand_consumes_identifier(source):
    checker = make_checker(source)
    checker.operand()
    assert checker._at_end() is True


@pytest.mark.parametrize("source", ["0", "12", "007", "9"])
def test_operand_consumes_constant(source):
    checker = make_checker(source)
    checker.operand()
    assert checker._at_end() is True


def test_operand_consumes_parenthesised_expression():
    checker = make_checker("(a + b) rest")
    checker.operand()
    assert checker._i == 7
    checker._skip_spaces()
    assert checker._peek() == "r"


def test_operand_rejects_empty_parentheses():
    with pytest.raises(SyntaxErrorEx) as exc:
        check("()")
    assert exc.value.message.startswith(OPERAND_ERROR)
    assert exc.value.column == 2


def test_operand_does_not_consume_factorials():
    checker = make_checker("a!")
    checker.operand()
    assert checker._peek() == "!"


# --------------------------------------------------------------------------
# expression и finish
# --------------------------------------------------------------------------


def test_expression_and_finish_consume_whole_source():
    checker = make_checker("a + b")
    checker.expression()
    checker.finish()
    assert checker._at_end() is True


def test_finish_rejects_leftover_characters():
    checker = make_checker("a b")
    checker.operand()
    with pytest.raises(SyntaxErrorEx) as exc:
        checker.finish()
    assert exc.value.message == "Лишний символ 'b' после выражения"
    assert exc.value.column == 3


def test_finish_is_silent_when_nothing_left():
    checker = make_checker("a")
    checker.expression()
    assert checker.finish() is None


# --------------------------------------------------------------------------
# SyntaxErrorEx: атрибуты и форматирование
# --------------------------------------------------------------------------


def test_syntax_error_exposes_message_line_and_column():
    error = SyntaxErrorEx("беда", "ab\ncd", 4)
    assert error.message == "беда"
    assert (error.line, error.column) == (2, 2)


def test_syntax_error_on_first_line_has_column_equal_to_pos_plus_one():
    error = SyntaxErrorEx("беда", "abcdef", 3)
    assert (error.line, error.column) == (1, 4)


def test_syntax_error_at_position_zero():
    error = SyntaxErrorEx("беда", "abc", 0)
    assert (error.line, error.column) == (1, 1)
    assert str(error).endswith("  abc\n  ^")


def test_syntax_error_without_source_has_empty_excerpt():
    assert str(SyntaxErrorEx("беда", "", 0)).splitlines()[-1] == "  ^"


def test_syntax_error_str_contains_position_excerpt_and_caret():
    error = SyntaxErrorEx("беда", "ab\ncd", 4)
    assert str(error) == "беда\n  позиция: строка 2, столбец 2\n  cd\n   ^"


def test_syntax_error_is_exception_and_message_is_first_line():
    error = SyntaxErrorEx("беда", "abc", 1)
    assert isinstance(error, Exception)
    assert str(error).splitlines()[0] == "беда"


def test_syntax_error_from_check_reports_position():
    with pytest.raises(SyntaxErrorEx) as exc:
        check("a +\n* b")
    error = exc.value
    assert error.message.startswith(OPERAND_ERROR)
    assert (error.line, error.column) == (2, 1)
    assert "позиция: строка 2, столбец 1" in str(error)
    assert "* b" in str(error)


# --------------------------------------------------------------------------
# check: корректные выражения
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "a",
        "5",
        "007",
        "_x",
        "имя",
        "变量",
        "(a)",
        "((a))",
        "(((a + b)))",
        "+a",
        "-a",
        "-(-a)",
        "-(a)",
        "+(-3)",
        "+-a",
        "- - a",
        "!a",
        "!5",
        "!!a",
        "-!a",
        "!-a",
        "! (a) !",
        "!(2 != 2)",
        "!(a + b) * c",
        "!((a))",
        "a!",
        "a!!!",
        "a! !",
        "a+b",
        "a-b",
        "a*b/c%d",
        "a < b",
        "a > b",
        "a <= b",
        "a >= b",
        "a == b",
        "a != b",
        "a && b",
        "a || b",
        "1+2*3",
        "a + b * c",
        "a < b && c > d",
        "(a+b)*c",
        "a + (b)",
        "a + (b * (c - d))",
        "a! + b",
        "a ! + b",
        "a != b",
        "a! != b",
        "-5!",
        "((a)! + b)!",
        "  a  ",
        "\ta\n",
        "a\n+\nb",
    ],
)
def test_check_accepts_valid_expression(source):
    assert check(source) is None


@pytest.mark.parametrize("op", BINARY_OPS)
def test_check_accepts_every_binary_operator(op):
    assert check(f"a {op} b") is None


def test_check_does_not_print_anything_on_success(capsys):
    check("a + b")
    assert capsys.readouterr() == ("", "")


# --------------------------------------------------------------------------
# check: некорректные выражения
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, fragment",
    [
        ("", OPERAND_ERROR),
        ("   ", OPERAND_ERROR),
        ("(", OPERAND_ERROR),
        (")", OPERAND_ERROR),
        ("+", OPERAND_ERROR),
        ("-", OPERAND_ERROR),
        ("*a", OPERAND_ERROR),
        ("a +", OPERAND_ERROR),
        ("a + ", OPERAND_ERROR),
        ("a * * b", OPERAND_ERROR),
        ("a + -b", OPERAND_ERROR),
        ("a + +b", OPERAND_ERROR),
        ("&&a", OPERAND_ERROR),
        ("a &&", OPERAND_ERROR),
        ("a <", OPERAND_ERROR),
        ("!", OPERAND_ERROR),
        ("!!", OPERAND_ERROR),
        ("!(", OPERAND_ERROR),
        ("!(1) == !(2)", OPERAND_ERROR),
        ("a + !b", OPERAND_ERROR),
        ("a + -b", OPERAND_ERROR),
        ("a)", EXTRA_CHAR_ERROR),
        ("a b", EXTRA_CHAR_ERROR),
        ("1 2", EXTRA_CHAR_ERROR),
        ("a!!b", EXTRA_CHAR_ERROR),
        ("a + b!", EXTRA_CHAR_ERROR),
        ("a + (b)!", EXTRA_CHAR_ERROR),
        ("a != b!", EXTRA_CHAR_ERROR),
        ("a\nb", EXTRA_CHAR_ERROR),
        ("(a+b", EXPECTED_RPAREN),
        ("(a b)", EXPECTED_RPAREN),
        ("a & b", EXTRA_CHAR_ERROR),
        ("a = b", EXTRA_CHAR_ERROR),
        ("a $ b", EXTRA_CHAR_ERROR),
    ],
)
def test_check_rejects_invalid_expression(source, fragment):
    with pytest.raises(SyntaxErrorEx) as exc:
        check(source)
    assert fragment in exc.value.message


def test_check_rejects_unknown_symbol_after_operand():
    with pytest.raises(SyntaxErrorEx) as exc:
        check("a $ b")
    assert exc.value.message == "Лишний символ '$' после выражения"
    assert exc.value.column == 3


def test_check_rejects_binary_op_chain_without_operand():
    with pytest.raises(SyntaxErrorEx) as exc:
        check("a + * b")
    assert exc.value.message.startswith(OPERAND_ERROR)
    assert exc.value.column == 5


@pytest.mark.parametrize(
    "source",
    [
        "1 !== 2",
        "1!==2",
        "1 !==2",
        "12 !== 34",
        "-1 !== 2",
        "a !== b",
        "a!!=b",
    ],
)
def test_check_reads_bang_bang_equal_as_factorial_then_comparison(source):
    assert check(source) is None


@pytest.mark.parametrize(
    "source, column",
    [
        ("1 !==", 6),
        ("1!==", 5),
        ("12 !==", 7),
        ("a !==", 6),
    ],
)
def test_check_rejects_bang_bang_equal_without_right_operand(source, column):
    with pytest.raises(SyntaxErrorEx) as exc:
        check(source)
    assert exc.value.message == (
        "Ожидался операнд: имя, константа или '(' выражение ')'. Получено конец строки"
    )
    assert (exc.value.line, exc.value.column) == (1, column)


def test_check_rejects_bang_bang_equal_in_middle_of_comparison():
    with pytest.raises(SyntaxErrorEx) as exc:
        check("a !=== b")
    assert exc.value.message == (
        "Ожидался операнд: имя, константа или '(' выражение ')'. Получено '='"
    )
    assert exc.value.column == 6


def test_check_rejects_bang_equal_without_operands():
    with pytest.raises(SyntaxErrorEx) as exc:
        check("1 ==")
    assert exc.value.message.startswith(OPERAND_ERROR)
    assert exc.value.column == 5


def test_check_reads_bang_equal_after_number_as_inequality():
    assert check("1 != 2") is None
    assert check("1!=2") is None


def test_check_treats_single_bang_after_number_as_factorial():
    assert check("1!") is None
    assert check("1 !") is None


def test_check_rejects_unclosed_nested_parenthesis():
    with pytest.raises(SyntaxErrorEx) as exc:
        check("((a + b)")
    assert exc.value.message.startswith(EXPECTED_RPAREN)
    assert exc.value.column == 9


@pytest.mark.parametrize(
    "source, line, column",
    [
        ("", 1, 1),
        ("a)", 1, 2),
        ("a b", 1, 3),
        ("a +", 1, 4),
        ("a + ", 1, 5),
        ("a\nb", 2, 1),
        ("a +\n* b", 2, 1),
        ("a\n\n  $", 3, 3),
        ("(a\n+ b", 2, 4),
    ],
)
def test_check_error_position(source, line, column):
    with pytest.raises(SyntaxErrorEx) as exc:
        check(source)
    assert (exc.value.line, exc.value.column) == (line, column)


def test_error_at_eof_without_trailing_newline_is_reported():
    with pytest.raises(SyntaxErrorEx) as exc:
        check("a +")
    assert (exc.value.line, exc.value.column) == (1, 4)


@pytest.mark.xfail(
    raises=IndexError,
    strict=True,
    reason=(
        "Баг модуля: при ошибке в конце строки, завершённой '\\n', "
        "source.splitlines() не содержит строки с номером line, "
        "и построение подсказки падает с IndexError вместо SyntaxErrorEx."
    ),
)
@pytest.mark.parametrize("source", ["a +\n", "\n", "a + \n"])
def test_error_at_eof_after_trailing_newline_reports_syntax_error(source):
    with pytest.raises(SyntaxErrorEx):
        check(source)


# --------------------------------------------------------------------------
# константы модуля
# --------------------------------------------------------------------------


def test_ops_constants_are_tuples():
    assert isinstance(BINARY_OPS, tuple)
    assert isinstance(PREFIX_OPS, tuple)


def test_binary_ops_content():
    assert set(BINARY_OPS) == {
        "+", "-", "*", "/", "%", "<", ">", "<=", ">=", "==", "!=", "&&", "||",
    }


def test_prefix_ops_are_signs():
    assert PREFIX_OPS == ("+", "-", "!")


def test_every_two_char_op_precedes_its_one_char_prefix():
    for op in BINARY_OPS:
        for shorter in (op[:1], op[:2]):
            if shorter in BINARY_OPS and shorter != op:
                assert BINARY_OPS.index(shorter) > BINARY_OPS.index(op)


def test_bang_equal_is_binary_op_not_factorial():
    assert "!=" in BINARY_OPS
    assert "!" not in BINARY_OPS


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def test_main_with_valid_argv_source_returns_zero(capsys):
    assert main(["syntax_check.py", "a + b * (c - 1)"]) == 0
    assert capsys.readouterr().out == "Синтаксис корректен.\n"


def test_main_uses_only_first_argument(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("!"))
    assert main(["syntax_check.py", "a+b", "?"]) == 0
    assert capsys.readouterr().out == "Синтаксис корректен.\n"


def test_main_with_invalid_argv_source_returns_one_and_prints_error(capsys):
    assert main(["syntax_check.py", "a +"]) == 1
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].startswith(f"Ошибка: {OPERAND_ERROR}")
    assert lines[0].endswith("Получено конец строки")
    assert "позиция: строка 1, столбец 4" in out
    assert "  a +\n     ^" in out


def test_main_reports_leftover_character_from_argv(capsys):
    assert main(["syntax_check.py", "a = b"]) == 1
    assert capsys.readouterr().out.splitlines()[0] == (
        "Ошибка: Лишний символ '=' после выражения"
    )


def test_main_without_argument_reads_stdin(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("a && (b || c)"))
    assert main(["syntax_check.py"]) == 0
    assert capsys.readouterr().out == "Синтаксис корректен.\n"


def test_main_with_empty_stdin_reports_error(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["syntax_check.py"]) == 1
    assert OPERAND_ERROR in capsys.readouterr().out


def test_main_with_multiline_stdin_reports_correct_line(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("a +\n* b"))
    assert main(["syntax_check.py"]) == 1
    out = capsys.readouterr().out
    assert "позиция: строка 2, столбец 1" in out
    assert "* b" in out


# --------------------------------------------------------------------------
# запуск модуля как скрипта
# --------------------------------------------------------------------------


MODULE_PATH = Path(__file__).with_name("syntax_check.py")


def run_script(args=(), stdin=""):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=MODULE_PATH.parent,
    )


def test_script_prints_success_and_exits_zero_for_argv_source():
    result = run_script(["a + b"])
    assert result.returncode == 0
    assert result.stdout == "Синтаксис корректен.\n"
    assert result.stderr == ""


def test_script_exits_one_and_prints_error_for_bad_source():
    result = run_script(["a + / b"])
    assert result.returncode == 1
    assert OPERAND_ERROR in result.stdout
    assert "позиция: строка 1, столбец 5" in result.stdout


def test_script_reads_expression_from_stdin():
    result = run_script(stdin="(a + b) * c\n")
    assert result.returncode == 0
    assert result.stdout == "Синтаксис корректен.\n"


def test_script_reports_leftover_character_with_nonzero_exit():
    result = run_script(["a = b"])
    assert result.returncode == 1
    assert "Лишний символ '='" in result.stdout