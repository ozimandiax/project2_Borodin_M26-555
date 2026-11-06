import json
import os

from primitive_db.constants import (
    CONTROL_CHARACTER_LIMIT,
    DATA_DIR,
    FILE_COPY_CHUNK_SIZE,
    JSON_ENCODING,
    JSON_INDENT,
    TABLE_FILE_EXTENSION,
    TABLE_INVALID_CHARACTERS,
    TABLE_RESERVED_NAMES,
    TEMP_FILE_MODE,
    TEMP_FILE_PREFIX,
    TEMP_FILE_SUFFIX,
    TEMP_FILE_TOKEN_BYTES,
)


def _load_json(filepath, default):
    """Прочитать JSON или вернуть значение для отсутствующего файла."""
    try:
        with open(filepath, encoding=JSON_ENCODING) as data_file:
            return json.load(data_file)
    except FileNotFoundError:
        return default


def _create_temporary_file(filepath, mode, **options):
    """Создать уникальный файл рядом с целевым для атомарной замены."""
    directory = os.path.dirname(os.path.abspath(filepath))
    while True:
        token = os.urandom(TEMP_FILE_TOKEN_BYTES).hex()
        temporary_path = os.path.join(
            directory, f"{TEMP_FILE_PREFIX}{token}{TEMP_FILE_SUFFIX}"
        )
        try:
            descriptor = os.open(
                temporary_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                TEMP_FILE_MODE,
            )
        except FileExistsError:
            continue
        break
    try:
        return temporary_path, os.fdopen(descriptor, mode, **options)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            # fdopen может сам закрыть дескриптор перед исключением.
            pass
        _discard_temporary_file(temporary_path)
        raise


def _discard_temporary_file(filepath):
    """Удалить временный файл, не скрывая результат основной операции."""
    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass
    except OSError as error:
        print(f'Не удалось удалить временный файл "{filepath}": {error}')


def _save_json(filepath, data):
    """Заменить JSON только после полной записи и закрытия временного файла."""
    serialized = json.dumps(data, ensure_ascii=False, indent=JSON_INDENT)
    temporary_path, data_file = _create_temporary_file(
        filepath, "w", encoding=JSON_ENCODING, newline="\n"
    )
    try:
        with data_file:
            data_file.write(serialized)
            data_file.write("\n")
            data_file.flush()
            os.fsync(data_file.fileno())
        os.replace(temporary_path, filepath)
    finally:
        _discard_temporary_file(temporary_path)


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


def _backup_table_file(table_path):
    """Сохранить байты таблицы в соседний файл перед её удалением."""
    with open(table_path, "rb") as source:
        backup_path, backup = _create_temporary_file(table_path, "wb")
        try:
            with backup:
                while chunk := source.read(FILE_COPY_CHUNK_SIZE):
                    backup.write(chunk)
                backup.flush()
                os.fsync(backup.fileno())
        except BaseException:
            _discard_temporary_file(backup_path)
            raise
    return backup_path


def delete_table(table_name, metadata_filepath, updated_metadata):
    """Удалить таблицу и сохранить метаданные с откатом при ошибке записи."""
    table_path = get_table_path(table_name)
    try:
        backup_path = _backup_table_file(table_path)
    except FileNotFoundError:
        save_metadata(metadata_filepath, updated_metadata)
        return

    try:
        delete_table_data(table_name)
    except BaseException:
        _discard_temporary_file(backup_path)
        raise

    try:
        save_metadata(metadata_filepath, updated_metadata)
    except BaseException:
        try:
            os.replace(backup_path, table_path)
        except OSError as error:
            raise OSError(
                f'Не удалось восстановить таблицу "{table_name}". '
                f'Резервная копия сохранена в "{backup_path}".'
            ) from error
        raise

    _discard_temporary_file(backup_path)
