from primitive_db.constants import ID_COLUMN, ID_NAME, TYPE_CLASSES, VALID_TYPES
from primitive_db.utils import get_table_path, load_table_data


def prepare_columns(columns):
    """Проверить столбцы и подготовить схему с системным ID."""
    prepared_columns = [ID_COLUMN]
    column_names = set()

    for column in columns:
        if not isinstance(column, str):
            raise ValueError("Ошибка: Описание столбца должно быть строкой.")
        column_name, separator, column_type = column.partition(":")

        if not separator or not column_name.strip() or column_type not in VALID_TYPES:
            raise ValueError(
                f"Некорректное значение: {column}. Попробуйте снова."
            )

        if column_name in column_names:
            raise ValueError(f'Ошибка: Столбец "{column_name}" повторяется.')

        column_names.add(column_name)

        if column_name == ID_NAME:
            if column != ID_COLUMN:
                raise ValueError(
                    f"Ошибка: Системный столбец должен быть {ID_COLUMN}."
                )
            continue

        prepared_columns.append(column)

    return prepared_columns


def create_table(metadata, table_name, columns):
    """Добавить таблицу с проверенной схемой в метаданные."""
    table_path = get_table_path(table_name)

    if table_name in metadata:
        raise ValueError(f'Ошибка: Таблица "{table_name}" уже существует.')

    for existing_name in metadata:
        if get_table_path(existing_name) == table_path:
            raise ValueError(
                f'Ошибка: Таблицы "{table_name}" и "{existing_name}" '
                "используют один файл данных."
            )

    prepared_columns = prepare_columns(columns)
    metadata[table_name] = prepared_columns
    return metadata


def drop_table(metadata, table_name):
    """Удалить существующую таблицу из метаданных."""
    if table_name not in metadata:
        raise ValueError(f'Ошибка: Таблица "{table_name}" не существует.')

    del metadata[table_name]
    return metadata


def get_schema(metadata, table_name):
    """Получить проверенную схему существующей таблицы."""
    if table_name not in metadata:
        raise KeyError(f'Ошибка: Таблица "{table_name}" не существует.')

    columns = metadata[table_name]
    if not isinstance(columns, list) or not columns:
        raise ValueError(f'Ошибка: Схема таблицы "{table_name}" повреждена.')
    if prepare_columns(columns) != columns:
        raise ValueError(f'Ошибка: Схема таблицы "{table_name}" повреждена.')

    return {
        column.partition(":")[0]: column.partition(":")[2]
        for column in columns
    }


def _validate_value(column_name, value, column_type):
    """Проверить точный тип значения без смешивания bool и int."""
    if type(value) is not TYPE_CLASSES[column_type]:
        raise ValueError(
            f'Ошибка: Значение столбца "{column_name}" '
            f"должно иметь тип {column_type}."
        )


def validate_clause(schema, clause, allow_id=True):
    """Проверить имена и типы полей условия или обновления."""
    if clause is None:
        return None
    if not isinstance(clause, dict) or not clause:
        raise ValueError("Ошибка: Условие должно содержать столбец и значение.")

    for column_name, value in clause.items():
        if column_name not in schema:
            raise KeyError(f'Ошибка: Столбец "{column_name}" не существует.')
        if not allow_id and column_name == ID_NAME:
            raise ValueError("Ошибка: Системный ID нельзя изменять.")
        _validate_value(column_name, value, schema[column_name])

    return clause


def validate_table_data(schema, table_data):
    """Проверить поля, типы и уникальность ID загруженных записей."""
    if not isinstance(table_data, list):
        raise ValueError("Ошибка: Данные таблицы должны быть списком записей.")

    identifiers = set()
    for row in table_data:
        if not isinstance(row, dict) or set(row) != set(schema):
            raise ValueError("Ошибка: Поля записи не соответствуют схеме таблицы.")
        for column_name, column_type in schema.items():
            _validate_value(column_name, row[column_name], column_type)

        identifier = row[ID_NAME]
        if identifier <= 0 or identifier in identifiers:
            raise ValueError(
                "Ошибка: ID записей должны быть положительными и уникальными."
            )
        identifiers.add(identifier)

    return table_data


def insert(metadata, table_name, values, table_data=None):
    """Проверить значения и вернуть данные с новой записью и уникальным ID."""
    schema = get_schema(metadata, table_name)
    value_columns = [name for name in schema if name != ID_NAME]
    if not isinstance(values, (list, tuple)) or len(values) != len(value_columns):
        raise ValueError(
            f"Ошибка: Ожидалось значений без ID: {len(value_columns)}."
        )

    for column_name, value in zip(value_columns, values):
        _validate_value(column_name, value, schema[column_name])

    if table_data is None:
        table_data = load_table_data(table_name)
    validate_table_data(schema, table_data)

    identifier = max((row[ID_NAME] for row in table_data), default=0) + 1
    record = {ID_NAME: identifier}
    record.update(zip(value_columns, values))
    return [*table_data, record]


def matches_clause(record, where_clause):
    """Сопоставить запись с равенствами, учитывая точные типы значений."""
    if where_clause is None:
        return True
    return all(
        column_name in record
        and type(record[column_name]) is type(value)
        and record[column_name] == value
        for column_name, value in where_clause.items()
    )


def select(table_data, where_clause=None):
    """Вернуть копии всех записей или записей, подходящих условию."""
    return [
        row.copy() for row in table_data if matches_clause(row, where_clause)
    ]


def _require_condition(where_clause):
    """Потребовать непустое условие для изменения или удаления записей."""
    if not isinstance(where_clause, dict) or not where_clause:
        raise ValueError("Ошибка: Для изменения данных необходимо условие where.")


def update(table_data, set_clause, where_clause):
    """Вернуть обновлённые записи без частичного изменения исходных данных."""
    _require_condition(where_clause)
    if not isinstance(set_clause, dict) or not set_clause:
        raise ValueError("Ошибка: Не заданы поля для обновления.")
    if ID_NAME in set_clause:
        raise ValueError("Ошибка: Системный ID нельзя изменять.")

    updated_data = []
    for row in table_data:
        updated_row = row.copy()
        if matches_clause(row, where_clause):
            for column_name, value in set_clause.items():
                if column_name not in row:
                    raise KeyError(f'Ошибка: Столбец "{column_name}" не существует.')
                if type(value) is not type(row[column_name]):
                    raise ValueError(
                        f'Ошибка: Тип столбца "{column_name}" нельзя изменять.'
                    )
            updated_row.update(set_clause)
        updated_data.append(updated_row)

    return updated_data


def delete(table_data, where_clause):
    """Вернуть записи, не соответствующие условию удаления."""
    _require_condition(where_clause)
    return [
        row.copy() for row in table_data if not matches_clause(row, where_clause)
    ]
