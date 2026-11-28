"""Проверки функций рисования.

Рисование устроено как канал команд: компилятор выпускает ``DRAW``, машина
складывает команды в ``Machine.drawings``, а GUI читает этот список и рисует
на холсте. Поэтому здесь проверяются и байт-код, и накопленные команды.
"""

import pytest

from gui.controller import DebugSession
from stack_compiler import (
    CompileError,
    CompileRuntimeError,
    Machine,
    compile_expression,
    compile_program,
    execute,
)


def run(source: str) -> Machine:
    machine = Machine(compile_program(source))
    machine.run()
    return machine


def run_error(source: str) -> Machine:
    machine = Machine(compile_program(source))
    with pytest.raises(CompileRuntimeError):
        machine.run()
    return machine


# --------------------------------------------------------------------------
# компиляция
# --------------------------------------------------------------------------


def test_point_instruction_is_generated():
    assert compile_program("point(10, 20);") == [
        ("PUSH", 10),
        ("PUSH", 20),
        ("DRAW", "point", 2),
        ("POP",),
    ]


@pytest.mark.parametrize(
    "source, expected",
    [
        (
            "line(1, 2, 3, 4);",
            [
                ("PUSH", 1),
                ("PUSH", 2),
                ("PUSH", 3),
                ("PUSH", 4),
                ("DRAW", "line", 4),
                ("POP",),
            ],
        ),
        (
            "rect(1, 2, 3, 4);",
            [
                ("PUSH", 1),
                ("PUSH", 2),
                ("PUSH", 3),
                ("PUSH", 4),
                ("DRAW", "rect", 4),
                ("POP",),
            ],
        ),
        (
            "circle(1, 2, 3);",
            [
                ("PUSH", 1),
                ("PUSH", 2),
                ("PUSH", 3),
                ("DRAW", "circle", 3),
                ("POP",),
            ],
        ),
        (
            'text(1, 2, "x");',
            [
                ("PUSH", 1),
                ("PUSH", 2),
                ("PUSH", "x"),
                ("DRAW", "text", 3),
                ("POP",),
            ],
        ),
        ("clear();", [("DRAW", "clear", 0), ("POP",)]),
        ('color("red");', [("PUSH", "red"), ("DRAW", "color", 1), ("POP",)]),
        ("linewidth(3);", [("PUSH", 3), ("DRAW", "linewidth", 1), ("POP",)]),
    ],
)
def test_draw_instruction_is_generated(source, expected):
    assert compile_program(source) == expected


def test_draw_returns_zero():
    assert execute(compile_expression("point(1, 2)")) == 0


# --------------------------------------------------------------------------
# команды рисования
# --------------------------------------------------------------------------


def test_point_is_recorded():
    machine = run("point(10, 20);")
    assert machine.drawings == [
        {"op": "point", "x": 10, "y": 20, "color": "black", "width": 2}
    ]


def test_line_is_recorded():
    machine = run("line(1, 2, 3, 4);")
    assert machine.drawings == [
        {
            "op": "line",
            "x1": 1,
            "y1": 2,
            "x2": 3,
            "y2": 4,
            "color": "black",
            "width": 2,
        }
    ]


def test_rect_is_recorded():
    machine = run("rect(1, 2, 3, 4);")
    assert machine.drawings == [
        {
            "op": "rect",
            "x1": 1,
            "y1": 2,
            "x2": 3,
            "y2": 4,
            "color": "black",
            "width": 2,
        }
    ]


def test_circle_is_recorded():
    machine = run("circle(5, 6, 7);")
    assert machine.drawings == [
        {"op": "circle", "x": 5, "y": 6, "r": 7, "color": "black", "width": 2}
    ]


def test_text_is_recorded():
    machine = run('text(5, 6, "привет");')
    assert machine.drawings == [
        {
            "op": "text",
            "x": 5,
            "y": 6,
            "text": "привет",
            "color": "black",
            "width": 2,
        }
    ]


def test_float_coordinates_are_allowed():
    machine = run("point(1.5, 2.5);")
    assert machine.drawings[0]["x"] == 1.5
    assert machine.drawings[0]["y"] == 2.5


def test_color_and_linewidth_apply_to_next_shapes():
    machine = run('color("red"); linewidth(5); line(0, 0, 10, 10);')
    assert machine.drawings == [
        {
            "op": "line",
            "x1": 0,
            "y1": 0,
            "x2": 10,
            "y2": 10,
            "color": "red",
            "width": 5,
        }
    ]


def test_color_and_linewidth_do_not_draw_by_themselves():
    machine = run('color("red"); linewidth(5);')
    assert machine.drawings == []


def test_clear_resets_screen_and_pen():
    machine = run(
        'color("red"); linewidth(5); point(1, 1); '
        "clear(); point(2, 2);"
    )
    assert [command["op"] for command in machine.drawings] == [
        "point",
        "clear",
        "point",
    ]
    assert machine.drawings[0]["color"] == "red"
    assert machine.drawings[0]["width"] == 5
    assert machine.drawings[2]["color"] == "black"
    assert machine.drawings[2]["width"] == 2


def test_drawings_are_part_of_snapshot():
    machine = run("point(1, 2);")
    assert machine.snapshot()["drawings"] == machine.drawings
    assert machine.snapshot()["pen_color"] == "black"


def test_drawings_are_cleared_on_reset():
    machine = run("point(1, 2);")
    assert machine.drawings
    machine.reset()
    assert machine.drawings == []


def test_goroutine_shares_drawings_with_main_machine():
    source = """\
func int draw() {
    point(1, 2);
    return 0;
}
go worker = draw();
sync();
"""
    machine = Machine(compile_program(source))
    machine.run()
    assert [command["op"] for command in machine.drawings] == ["point"]


def test_debug_session_exposes_drawings():
    session = DebugSession()
    session.set_source("point(1, 2);")
    assert session.compile()
    session.run_all()
    assert session.drawings == [
        {"op": "point", "x": 1, "y": 2, "color": "black", "width": 2}
    ]
    assert session.snapshot()["drawings"] == session.drawings


def test_debug_session_drawings_revision_tracks_new_commands_and_reset():
    session = DebugSession()
    session.set_source("point(1, 2);")
    assert session.compile()
    generation, count = session.drawings_revision
    session.run_all()
    assert session.drawings_revision == (generation, count + 1)
    session.reset()
    new_generation, new_count = session.drawings_revision
    assert new_generation > generation
    assert new_count == 0


# --------------------------------------------------------------------------
# ошибки компиляции и выполнения
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, match",
    [
        ("point(1);", "ожидает 2"),
        ("line(1, 2, 3);", "ожидает 4"),
        ("circle(1, 2);", "ожидает 3"),
        ("clear(1);", "ожидает 0"),
        ('point("a", 1);', "должен иметь числовой тип"),
        ('color(1);', "должен иметь тип string"),
        ('text(1, 2, 3);', "должен иметь тип string"),
    ],
)
def test_draw_argument_errors(source, match):
    with pytest.raises(CompileError, match=match):
        compile_program(source)


def test_draw_function_names_are_reserved():
    with pytest.raises(CompileError, match="совпадает со встроенной"):
        compile_program("func int point(int x) { return x; }")


def test_negative_circle_radius_is_a_runtime_error():
    machine = run_error("circle(0, 0, -1);")
    assert machine.status == "error"
    assert "радиус" in str(machine.error)


def test_non_positive_linewidth_is_a_runtime_error():
    machine = run_error("linewidth(0);")
    assert machine.status == "error"
    assert "толщина" in str(machine.error)


def test_empty_color_is_a_runtime_error():
    machine = run_error('color("");')
    assert machine.status == "error"
    assert "цвет" in str(machine.error)
