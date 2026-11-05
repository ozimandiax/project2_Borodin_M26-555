import json
import shlex

import prompt

from primitive_db.constants import COMMANDS, META_FILE
from primitive_db.core import create_table, drop_table
from primitive_db.utils import load_metadata, save_metadata


def print_help():
    """Вывести список доступных команд."""
    print("\n***Процесс работы с таблицей***")
    print("Функции:")
    print(
        "<command> create_table <имя_таблицы> <столбец1:тип> ... "
        "- создать таблицу"
    )
    print("<command> list_tables - показать список всех таблиц")
    print("<command> drop_table <имя_таблицы> - удалить таблицу")
    print("<command> exit - выйти из программы")
    print("<command> help - справочная информация")


def has_valid_arguments(args):
    """Проверить количество аргументов известной команды."""
    if args[0] == "create_table":
        return len(args) >= 3
    if args[0] == "drop_table":
        return len(args) == 2
    return len(args) == 1


def execute_command(args, metadata):
    """Выполнить команду таблиц и сохранить успешное изменение."""
    command = args[0]

    if command == "create_table":
        table_name = args[1]
        metadata = create_table(metadata, table_name, args[2:])
        save_metadata(META_FILE, metadata)
        columns = ", ".join(metadata[table_name])
        print(
            f'Таблица "{table_name}" успешно создана со столбцами: {columns}'
        )
    elif command == "drop_table":
        table_name = args[1]
        metadata = drop_table(metadata, table_name)
        save_metadata(META_FILE, metadata)
        print(f'Таблица "{table_name}" успешно удалена.')
    elif command == "list_tables":
        if metadata:
            for table_name in metadata:
                print(f"- {table_name}")
        else:
            print("Таблиц пока нет.")


def run():
    """Запустить цикл команд с загрузкой актуальных метаданных."""
    print_help()

    while True:
        try:
            user_input = prompt.string("Введите команду: ", empty=True).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        try:
            args = shlex.split(user_input)
        except ValueError:
            print(f"Некорректное значение: {user_input}. Попробуйте снова.")
            continue

        if not args:
            continue

        command = args[0]
        if command not in COMMANDS:
            print(f"Функции {command} нет. Попробуйте снова.")
            continue

        if not has_valid_arguments(args):
            print(f"Некорректное значение: {user_input}. Попробуйте снова.")
            continue

        if command == "exit":
            break
        if command == "help":
            print_help()
            continue

        try:
            metadata = load_metadata(META_FILE)
            execute_command(args, metadata)
        except json.JSONDecodeError:
            print("Ошибка: Файл метаданных содержит некорректный JSON.")
        except ValueError as error:
            print(error)
        except OSError as error:
            print(f"Ошибка работы с файлом: {error}")
