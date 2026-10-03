class SymbolTable:
    def __init__(self):
        # Сам словарь: { 'имя_переменной': { 'type': 'int', 'value': значение } }
        self._variables = {}

    def declare(self, name: str, value: int = None):
        """
        Метод для объявления переменной (соответствует int ИМЯ [=число]).
        Если value не передано (None), переменная объявляется как неинициализированная.
        """
        if not name.isidentifier():
            raise ValueError(f"Ошибка синтаксиса: '{name}' не является валидным именем переменной.")
        
        if name in self._variables:
            raise NameError(f"Ошибка семантики: Переменная '{name}' уже объявлена.")

        # Заносим в словарь структуру с типом и значением
        self._variables[name] = {
            "type": "int",
            "value": value
        }
        
        status = f"инициализирована со значением {value}" if value is not None else "объявлена без значения"
        print(f"[Успех] Переменная '{name}' успешно {status}.")

    def assign(self, name: str, value: int):
        """
        Метод для изменения значения уже существующей переменной (для будущего расширения языка).
        """
        if name not in self._variables:
            raise NameError(f"Ошибка: Переменная '{name}' не объявлена.")
        
        if not isinstance(value, int):
            raise TypeError(f"Ошибка типов: Переменной '{name}' (int) нельзя присвоить {type(value).__name__}.")

        self._variables[name]["value"] = value
        print(f"[Успех] Переменной '{name}' присвоено новое значение {value}.")

    def get(self, name: str) -> int:
        """
        Метод для получения значения переменной.
        """
        if name not in self._variables:
            raise NameError(f"Ошибка: Переменная '{name}' не найдена.")
        
        value = self._variables[name]["value"]
        if value is None:
            raise ValueError(f"Ошибка выполнения: Переменная '{name}' использована до инициализации.")
            
        return value

    def __str__(self):
        """Красивый вывод таблицы символов"""
        if not self._variables:
            return "Таблица символов пуста."
        
        lines = ["--- Таблица символов ---", f"{'Имя':<12} | {'Тип':<6} | {'Значение':<8}"]
        lines.append("-" * 34)
        for name, info in self._variables.items():
            val = info['value'] if info['value'] is not None else "None (не инициализирована)"
            lines.append(f"{name:<12} | {info['type']:<6} | {val:<8}")
        return "\n".join(lines)


# ==========================================
# ДЕМОНСТРАЦИЯ РАБОТЫ (Тест-кейсы из РБНФ)
# ==========================================
if __name__ == "__main__":
    table = SymbolTable()

    print("--- 1. Парсинг строки: int x; ---")
    table.declare("x")

    print("\n--- 2. Парсинг строки: int count = 0; ---")
    table.declare("count", 0)

    print("\n--- 3. Парсинг строки: int a, b, c = 10; ---")
    # Имитация прохода парсера по списку через запятую
    table.declare("a")
    table.declare("b")
    table.declare("c", 10)

    # Выводим текущее состояние словаря
    print("\n" + str(table) + "\n")

    print("--- 4. Проверка обработки ошибок ---")
    try:
        # Попытка повторного объявления (int x;)
        table.declare("x", 5)
    except NameError as e:
        print(f"Перехвачено исключение: {e}")

    try:
        # Попытка прочитать переменную 'a', которая не была инициализирована
        table.get("a")
    except ValueError as e:
        print(f"Перехвачено исключение: {e}")

    try:
        # Попытка объявить переменную с недопустимым именем (например, с цифры)
        table.declare("1digit")
    except ValueError as e:
        print(f"Перехвачено исключение: {e}")
