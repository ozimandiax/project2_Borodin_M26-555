import json
import os

from primitive_db.constants import (
    CONTROL_CHARACTER_LIMIT,
    DATA_DIR,
    JSON_ENCODING,
    JSON_INDENT,
    TABLE_FILE_EXTENSION,
    TABLE_INVALID_CHARACTERS,
    TABLE_RESERVED_NAMES,
)


def _load_json(filepath, default):
    """Прочитать JSON или вернуть значение для отсутствующего файла."""
    try:
        with open(filepath, encoding=JSON_ENCODING) as data_file:
            return json.load(data_file)
    except FileNotFoundError:
        return default


def _save_json(filepath, data):
    """Проверить сериализацию и записать JSON в UTF-8."""
    serialized = json.dumps(data, ensure_ascii=False, indent=JSON_INDENT)
    with open(filepath, "w", encoding=JSON_ENCODING) as data_file:
        data_file.write(serialized)
        data_file.write("\n")


def load_metadata(filepath):
    """Загрузить метаданные или вернуть пустой словарь."""
    metadata = _load_json(filepath, {})

    if not isinstance(metadata, dict):
        raise ValueError("Ошибка: Метаданные должны содержать JSON-объект.")

    return metadata


def save_metadata(filepath, data):
    """Сохранить метаданные в JSON-файл."""
    if not isinstance(data, dict):
        raise ValueError("Ошибка: Метаданные должны содержать JSON-объект.")
    _save_json(filepath, data)


def get_table_path(table_name):
    """Получить путь таблицы без выхода за пределы каталога данных."""
    if (
        not isinstance(table_name, str)
        or not table_name.strip()
        or table_name in (".", "..")
        or table_name.endswith((".", " "))
        or any(character in TABLE_INVALID_CHARACTERS for character in table_name)
        or any(ord(character) < CONTROL_CHARACTER_LIMIT for character in table_name)
    ):
        raise ValueError("Ошибка: Недопустимое имя таблицы для файла данных.")

    if table_name.split(".", 1)[0].upper() in TABLE_RESERVED_NAMES:
        raise ValueError("Ошибка: Имя таблицы зарезервировано системой Windows.")

    data_directory = os.path.normcase(os.path.realpath(DATA_DIR))
    table_path = os.path.normcase(
        os.path.realpath(
            os.path.join(data_directory, f"{table_name}{TABLE_FILE_EXTENSION}")
        )
    )
    try:
        within_data_directory = (
            os.path.commonpath((data_directory, table_path)) == data_directory
        )
    except ValueError:
        within_data_directory = False

    if not within_data_directory:
        raise ValueError("Ошибка: Путь таблицы выходит за пределы каталога данных.")

    return table_path


def _validate_table_rows(data):
    """Проверить структуру JSON-массива записей."""
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError("Ошибка: Данные таблицы должны быть списком записей.")


def load_table_data(table_name):
    """Загрузить записи таблицы или вернуть пустой список."""
    data = _load_json(get_table_path(table_name), [])
    _validate_table_rows(data)
    return data


def save_table_data(table_name, data):
    """Сохранить записи таблицы в отдельный JSON-файл."""
    table_path = get_table_path(table_name)
    _validate_table_rows(data)
    os.makedirs(os.path.dirname(table_path), exist_ok=True)
    _save_json(table_path, data)


def delete_table_data(table_name):
    """Удалить файл таблицы, если он существует."""
    table_path = get_table_path(table_name)
    try:
        os.remove(table_path)
    except FileNotFoundError:
        pass
