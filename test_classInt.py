import pytest

from classInt import SymbolTable


@pytest.fixture
def table():
    return SymbolTable()


def test_declare_without_value_sets_none(table, capsys):
    table.declare("x")
    assert table._variables["x"] == {"type": "int", "value": None}
    assert "[Успех] Переменная 'x' успешно объявлена без значения." in capsys.readouterr().out


def test_declare_with_value(table, capsys):
    table.declare("count", 0)
    assert table.get("count") == 0
    assert "инициализирована со значением 0" in capsys.readouterr().out


def test_declare_negative_and_large_values(table):
    table.declare("neg", -42)
    table.declare("big", 10**18)
    assert table.get("neg") == -42
    assert table.get("big") == 10**18


@pytest.mark.parametrize(
    "value",
    [1.24, 1, -1, 255, 2**31 - 1, -(2**31)],
)
def test_declare_stores_value_verbatim(table, value):
    table.declare("n", value)
    assert table._variables["n"]["value"] == value


def test_declare_accepts_keyword_names(table):
    table.declare("class")
    table.declare("_private")
    table.declare("变量")
    assert set(table._variables) == {"class", "_private", "变量"}


def test_declare_multiple_variables(table):
    for name in ("a", "b"):
        table.declare(name)
    table.declare("c", 10)
    assert str(table).count("int") == 3


def test_declare_twice_raises_name_error(table):
    table.declare("x")
    with pytest.raises(NameError, match="Переменная 'x' уже объявлена"):
        table.declare("x")
    assert table._variables["x"]["value"] is None


def test_declare_twice_with_value_keeps_original(table):
    table.declare("x", 1)
    with pytest.raises(NameError):
        table.declare("x", 2)
    assert table.get("x") == 1


@pytest.mark.parametrize(
    "name",
    ["1digit", "my var", "my-var", "", "a.b", "#x", "9", "имя!"],
)
def test_declare_invalid_name_raises_value_error(table, name):
    with pytest.raises(ValueError, match="не является валидным именем"):
        table.declare(name)
    assert table._variables == {}


def test_declare_invalid_name_after_valid_declarations(table):
    table.declare("ok", 5)
    with pytest.raises(ValueError):
        table.declare("bad name")
    assert set(table._variables) == {"ok"}


def test_declare_then_assign(table):
    table.declare("x")
    table.assign("x", 7)
    assert table.get("x") == 7


def test_assign_undeclared_raises(table):
    with pytest.raises(NameError, match="не объявлена"):
        table.assign("ghost", 1)


def test_assign_wrong_type_raises_type_error(table):
    table.declare("x", 1)
    with pytest.raises(TypeError, match="нельзя присвоить str"):
        table.assign("x", "1")
    assert table.get("x") == 1


def test_get_undeclared_raises_name_error(table):
    with pytest.raises(NameError, match="не найдена"):
        table.get("nope")


def test_get_before_initialization_raises_value_error(table):
    table.declare("x")
    with pytest.raises(ValueError, match="использована до инициализации"):
        table.get("x")


def test_str_empty_table():
    assert str(SymbolTable()) == "Таблица символов пуста."


def test_str_contains_all_declarations(table):
    table.declare("a")
    table.declare("b", 10)
    output = str(table)
    assert "--- Таблица символов ---" in output
    assert "None (не инициализирована)" in output
    assert "a" in output and "b" in output
    assert "int" in output