"""Разобрать команды базы данных, сохраняя типы значений в кавычках."""

import shlex


def _tokenize(text):
    """Разделить текст на слова и знаки вне кавычек."""
    tokens = []
    position = 0

    while position < len(text):
        if text[position].isspace():
            position += 1
            continue

        if text[position] in "(),=":
            tokens.append(("symbol", text[position]))
            position += 1
            continue

        start = position
        quote = None
        first_quote_end = None

        while position < len(text):
            character = text[position]

            if quote is not None:
                if character == quote:
                    quote = None
                    if text[start] in "\"'" and first_quote_end is None:
                        first_quote_end = position
                elif character == "\\" and quote == '"':
                    position += 1
                    if position == len(text):
                        raise ValueError("Ошибка синтаксиса: незакрытая кавычка.")
            elif character.isspace() or character in "(),=":
                break
            elif character in "\"'":
                quote = character
            elif character == "\\":
                position += 1
                if position == len(text):
                    raise ValueError("Ошибка синтаксиса: незавершённое экранирование.")

            position += 1

        if quote is not None:
            raise ValueError("Ошибка синтаксиса: незакрытая кавычка.")

        raw_value = text[start:position]
        try:
            value = shlex.split(raw_value)[0]
        except (IndexError, ValueError) as error:
            raise ValueError("Ошибка синтаксиса: некорректные кавычки.") from error

        if first_quote_end == position - 1:
            kind = "quoted"
        elif any(character in "\"'" for character in raw_value):
            kind = "mixed"
        else:
            kind = "word"
        tokens.append((kind, value))

    return tokens


def _matches(tokens, position, expected):
    """Проверить знак или ключевое слово в текущей позиции."""
    if position >= len(tokens):
        return False
    kind, value = tokens[position]
    return kind in ("word", "symbol") and value.lower() == expected


def _expect(tokens, position, expected):
    """Прочитать обязательный знак или ключевое слово."""
    if not _matches(tokens, position, expected):
        raise ValueError(f'Ошибка синтаксиса: ожидалось "{expected}".')
    return position + 1


def _read_name(tokens, position):
    """Прочитать непустое имя таблицы или столбца."""
    if position >= len(tokens):
        raise ValueError("Ошибка синтаксиса: не указано имя таблицы или столбца.")
    kind, value = tokens[position]
    if kind == "symbol" or not value.strip():
        raise ValueError("Ошибка синтаксиса: некорректное имя таблицы или столбца.")
    return value, position + 1


def _read_value(tokens, position):
    """Прочитать строку в кавычках, целое число или логическое значение."""
    if position >= len(tokens):
        raise ValueError("Ошибка синтаксиса: не указано значение.")

    kind, value = tokens[position]
    if kind == "quoted":
        return value, position + 1

    if kind == "word":
        if value.lower() in ("true", "false"):
            return value.lower() == "true", position + 1
        digits = value[1:] if value[:1] in ("+", "-") else value
        if digits and digits.isdecimal():
            try:
                return int(value), position + 1
            except ValueError as error:
                raise ValueError("Некорректное целое число.") from error

    raise ValueError(
        f"Некорректное значение: {value}. "
        "Используйте целое число, true, false или строку в кавычках."
    )


def _read_assignment(tokens, position):
    """Прочитать одно равенство имени и значения."""
    column_name, position = _read_name(tokens, position)
    position = _expect(tokens, position, "=")
    value, position = _read_value(tokens, position)
    return {column_name: value}, position


def _read_set(tokens, position):
    """Прочитать присваивания, разделённые запятыми."""
    set_clause = {}
    while True:
        assignment, position = _read_assignment(tokens, position)
        column_name = next(iter(assignment))
        if column_name in set_clause:
            raise ValueError(f'Ошибка: Столбец "{column_name}" повторяется в set.')
        set_clause.update(assignment)
        if not _matches(tokens, position, ","):
            return set_clause, position
        position += 1


def _read_values(tokens, position):
    """Прочитать значения внутри круглых скобок."""
    position = _expect(tokens, position, "(")
    values = []
    if _matches(tokens, position, ")"):
        return values, position + 1

    while True:
        value, position = _read_value(tokens, position)
        values.append(value)
        if _matches(tokens, position, ")"):
            return values, position + 1
        position = _expect(tokens, position, ",")


def _require_end(tokens, position):
    """Отклонить лишние аргументы после законченной команды."""
    if position != len(tokens):
        raise ValueError("Ошибка синтаксиса: лишние аргументы в конце команды.")


def parse_values(expression):
    """Разобрать список значений вида (\"Имя\", 28, true)."""
    tokens = _tokenize(expression)
    values, position = _read_values(tokens, 0)
    _require_end(tokens, position)
    return values


def parse_where(expression):
    """Разобрать одно равенство без ключевого слова where."""
    tokens = _tokenize(expression)
    where_clause, position = _read_assignment(tokens, 0)
    _require_end(tokens, position)
    return where_clause


def parse_set(expression):
    """Разобрать присваивания без ключевого слова set."""
    tokens = _tokenize(expression)
    set_clause, position = _read_set(tokens, 0)
    _require_end(tokens, position)
    return set_clause


def _parse_create(tokens):
    """Разобрать создание таблицы со списком столбцов."""
    table_name, position = _read_name(tokens, 1)
    columns = []
    while position < len(tokens):
        column, position = _read_name(tokens, position)
        columns.append(column)
    if not columns:
        raise ValueError("Ошибка синтаксиса: укажите хотя бы один столбец.")
    return {"command": "create_table", "table_name": table_name, "columns": columns}


def _parse_insert(tokens):
    """Разобрать добавление записи в таблицу."""
    position = _expect(tokens, 1, "into")
    table_name, position = _read_name(tokens, position)
    position = _expect(tokens, position, "values")
    values, position = _read_values(tokens, position)
    _require_end(tokens, position)
    return {"command": "insert", "table_name": table_name, "values": values}


def _parse_select(tokens):
    """Разобрать выборку с необязательным условием."""
    position = _expect(tokens, 1, "from")
    table_name, position = _read_name(tokens, position)
    where_clause = None
    if position < len(tokens):
        position = _expect(tokens, position, "where")
        where_clause, position = _read_assignment(tokens, position)
    _require_end(tokens, position)
    return {
        "command": "select",
        "table_name": table_name,
        "where_clause": where_clause,
    }


def _parse_update(tokens):
    """Разобрать обновление полей с обязательным условием."""
    table_name, position = _read_name(tokens, 1)
    position = _expect(tokens, position, "set")
    set_clause, position = _read_set(tokens, position)
    position = _expect(tokens, position, "where")
    where_clause, position = _read_assignment(tokens, position)
    _require_end(tokens, position)
    return {
        "command": "update",
        "table_name": table_name,
        "set_clause": set_clause,
        "where_clause": where_clause,
    }


def _parse_delete(tokens):
    """Разобрать удаление записей с обязательным условием."""
    position = _expect(tokens, 1, "from")
    table_name, position = _read_name(tokens, position)
    position = _expect(tokens, position, "where")
    where_clause, position = _read_assignment(tokens, position)
    _require_end(tokens, position)
    return {
        "command": "delete",
        "table_name": table_name,
        "where_clause": where_clause,
    }


def parse_command(user_input):
    """Преобразовать команду в словарь аргументов или вернуть None."""
    tokens = _tokenize(user_input)
    if not tokens:
        return None

    command = tokens[0][1].lower()
    if command in ("help", "exit", "list_tables"):
        _require_end(tokens, 1)
        return {"command": command}
    if command in ("drop_table", "info"):
        table_name, position = _read_name(tokens, 1)
        _require_end(tokens, position)
        return {"command": command, "table_name": table_name}

    parsers = {
        "create_table": _parse_create,
        "insert": _parse_insert,
        "select": _parse_select,
        "update": _parse_update,
        "delete": _parse_delete,
    }
    if command not in parsers:
        raise ValueError(f"Функции {tokens[0][1]} нет. Попробуйте снова.")
    return parsers[command](tokens)
