import pytest

from gui.controller import DebugSession, format_instruction


def test_session_compiles_and_runs_program():
    session = DebugSession()
    assert session.compile("int i; i = 0; while i < 3 { i = i + 1; }")
    assert session.status == "ready"
    assert session.machine is not None
    assert session.machine.variables == {}
    session.run_all()
    assert session.machine.variables == {"i": 3}
    assert session.status == "finished"


def test_session_expression_mode_returns_result():
    session = DebugSession()
    assert session.compile("1 + 2 * 3", "expression")
    assert session.run_all() == 7
    assert session.status == "finished"


def test_session_compile_error_has_line_and_text():
    session = DebugSession()
    assert not session.compile("x = ;")
    assert session.status == "error"
    assert "Ожидался операнд" in session.error
    assert session.error_line == 1
    assert session.machine is None


def test_session_step_updates_stack_and_trace():
    session = DebugSession()
    assert session.compile("int x = 1;")
    session.step()
    assert session.machine.stack == [1]
    assert session.machine.pc == 1
    assert session.trace == ["0000  PUSH 1"]
    session.step()
    assert session.machine.variables == {"x": 1}
    assert session.machine.status == "finished"


def test_session_breakpoints_and_resume():
    session = DebugSession()
    assert session.compile("int x = 1;")
    assert session.toggle_breakpoint(0) is True
    assert session.at_breakpoint() is True
    session.resume()
    assert session.at_breakpoint() is False
    session.step()
    assert session.at_breakpoint() is False
    assert session.toggle_breakpoint(0) is False
    assert session.breakpoints == set()


def test_session_set_source_invalidates_machine():
    session = DebugSession()
    assert session.compile("int x = 1;")
    session.set_source("int x = 2;")
    assert session.machine is None
    assert session.code is None
    assert session.dirty is True
    assert session.ensure_compiled() is True
    session.run_all()
    assert session.machine.variables == {"x": 2}


def test_session_current_line_and_reset():
    session = DebugSession()
    assert session.compile("int x = 1;\nint y = 2;")
    assert session.current_line() == 1
    session.run_all()
    assert session.status == "finished"
    session.reset()
    assert session.status == "ready"
    assert session.machine.variables == {}
    assert session.trace == []


def test_session_exposes_declared_types():
    session = DebugSession()
    assert session.compile("int x = 1; int a[3];")
    assert session.types == {"x": "int", "a": "int[]"}
    assert session.snapshot()["types"] == {"x": "int", "a": "int[]"}


def test_session_snapshot_without_code():
    session = DebugSession()
    view = session.snapshot()
    assert view["status"] == "empty"
    assert view["code"] == []
    assert view["stack"] == []


def test_format_instruction():
    assert format_instruction(("PUSH", 1)) == "PUSH 1"
    assert format_instruction(("ADD",)) == "ADD"
