"""Система типов языка Stack Lang.

Скалярные типы:

    int      — целое число;
    float    — вещественное число;
    double   — вещественное число двойной точности;
    string   — строка.

Массивы типизированы по элементу: ``int[]``, ``float[]``, ``double[]``,
``string[]``.

Числовые типы упорядочены по точности: ``int < float < double``. Сужение
(``double`` -> ``float`` или ``int``) неявно запрещено — нужен явный вызов
преобразования. Расширение (``int`` -> ``float``) разрешено.

Типы выводятся компилятором во время разбора (одноходовый компилятор
не строит AST, поэтому тип выражения известен ровно тогда, когда разобран
его последний операнд). Здесь живут сам тип, таблица символов и сигнатуры
встроенных функций.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class Type(Enum):
    """Тип значения в языке."""

    INT = "int"
    FLOAT = "float"
    DOUBLE = "double"
    STRING = "string"
    INT_ARRAY = "int[]"
    FLOAT_ARRAY = "float[]"
    DOUBLE_ARRAY = "double[]"
    STRING_ARRAY = "string[]"

    def __str__(self) -> str:
        return self.value

    @property
    def is_numeric(self) -> bool:
        """Числовой ли это тип."""
        return self in NUMERIC_TYPES

    @property
    def is_array(self) -> bool:
        """Массив ли это тип."""
        return self in ARRAY_ELEMENTS

    @property
    def element(self) -> Type | None:
        """Тип элемента массива (``None`` для не-массивов)."""
        return ARRAY_ELEMENTS.get(self)

    @property
    def rank(self) -> int:
        """Ранг числового типа: ``int`` < ``float`` < ``double``."""
        return NUMERIC_RANKS[self]


NUMERIC_TYPES = frozenset({Type.INT, Type.FLOAT, Type.DOUBLE})

NUMERIC_RANKS = {Type.INT: 0, Type.FLOAT: 1, Type.DOUBLE: 2}

ARRAY_ELEMENTS = {
    Type.INT_ARRAY: Type.INT,
    Type.FLOAT_ARRAY: Type.FLOAT,
    Type.DOUBLE_ARRAY: Type.DOUBLE,
    Type.STRING_ARRAY: Type.STRING,
}

ELEMENT_ARRAYS = {element: array for array, element in ARRAY_ELEMENTS.items()}

#: Ключевые слова типов и соответствующие им типы.
TYPE_KEYWORDS = {
    "int": Type.INT,
    "float": Type.FLOAT,
    "double": Type.DOUBLE,
    "string": Type.STRING,
}

#: Имена ключевых слов типов в порядке поиска.
TYPE_KEYWORD_NAMES = tuple(TYPE_KEYWORDS)


def array_of(element: Type) -> Type:
    """Тип массива с элементами указанного типа."""
    return ELEMENT_ARRAYS[element]


def promote(left: Type, right: Type) -> Type:
    """Общий тип двух числовых операндов — по большей точности."""
    return left if NUMERIC_RANKS[left] >= NUMERIC_RANKS[right] else right


def assignable(target: Type, source: Type) -> bool:
    """Допустимо ли присвоить значение типа ``source`` в переменную ``target``.

    Равные типы — всегда. Числовые: разрешено расширение (``int`` -> ``float``
    -> ``double``), сужение запрещено. Массивы и строки преобразуются только
    явно.
    """
    if target is source:
        return True
    if target.is_numeric and source.is_numeric:
        return NUMERIC_RANKS[source] <= NUMERIC_RANKS[target]
    return False


def convert_kind(target: Type) -> str | None:
    """Имя вида преобразования для перехода ``source`` -> ``target``.

    ``None``, если преобразование на уровне рантайма не нужно.
    """
    if target in (Type.FLOAT, Type.DOUBLE, Type.INT, Type.STRING):
        return target.value
    return None


@dataclass(frozen=True)
class Symbol:
    """Запись в таблице символов."""

    name: str
    type: Type
    position: int  # позиция объявления в исходнике, -1 — внешняя переменная


@dataclass(frozen=True)
class Parameter:
    """Параметр пользовательской функции."""

    name: str
    type: Type


@dataclass
class FunctionDef:
    """Описание пользовательской функции.

    ``entry_pc`` заполняется после разбора тела: сигнатура известна раньше
    (это позволяет рекурсию), а адрес входа — только когда тело скомпилировано.
    """

    name: str
    parameters: tuple[Parameter, ...]
    return_type: Type
    entry_pc: int = -1
    position: int = -1

    @property
    def param_names(self) -> tuple[str, ...]:
        return tuple(parameter.name for parameter in self.parameters)

    @property
    def param_types(self) -> tuple[Type, ...]:
        return tuple(parameter.type for parameter in self.parameters)


def normalize_declared(
    declared: Iterable[str | tuple[str, Type]],
) -> dict[str, Type]:
    """Привести список внешних переменных к виду ``имя -> тип``.

    Принимает и просто имена (``'x'`` -> ``int``), и пары
    (``('x', Type.INT_ARRAY)`` -> ``int[]``).
    """
    result: dict[str, Type] = {}
    for item in declared:
        if isinstance(item, str):
            result[item] = Type.INT
        else:
            name, type_ = item
            result[name] = type_
    return result


class SymbolTable:
    """Таблица символов компилятора: имя -> объявленный тип.

    Областей видимости в языке нет, таблица плоская: объявление видно до
    конца программы.
    """

    def __init__(self, declared: Iterable[str | tuple[str, Type]] = ()) -> None:
        self._symbols: dict[str, Symbol] = {}
        for name, type_ in normalize_declared(declared).items():
            self._symbols[name] = Symbol(name, type_, -1)

    def declare(self, name: str, type_: Type, position: int) -> None:
        self._symbols[name] = Symbol(name, type_, position)

    def lookup(self, name: str) -> Symbol | None:
        return self._symbols.get(name)

    def as_types(self) -> dict[str, Type]:
        """Копия таблицы в виде ``имя -> тип`` (для GUI и диагностики)."""
        return {name: symbol.type for name, symbol in self._symbols.items()}

    def __contains__(self, name: str) -> bool:
        return name in self._symbols

    def __len__(self) -> int:
        return len(self._symbols)
