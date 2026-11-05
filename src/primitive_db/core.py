from primitive_db.constants import ID_COLUMN, ID_NAME, VALID_TYPES


def prepare_columns(columns):
    """Проверить столбцы и подготовить схему с системным ID."""
    prepared_columns = [ID_COLUMN]
    column_names = set()

    for column in columns:
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
    if not table_name.strip():
        raise ValueError("Ошибка: Имя таблицы не может быть пустым.")

    if table_name in metadata:
        raise ValueError(f'Ошибка: Таблица "{table_name}" уже существует.')

    prepared_columns = prepare_columns(columns)
    metadata[table_name] = prepared_columns
    return metadata


def drop_table(metadata, table_name):
    """Удалить существующую таблицу из метаданных."""
    if table_name not in metadata:
        raise ValueError(f'Ошибка: Таблица "{table_name}" не существует.')

    del metadata[table_name]
    return metadata
