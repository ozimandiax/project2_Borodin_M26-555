import json

import prompt
from prettytable import PrettyTable

from primitive_db.constants import ID_NAME, META_FILE
from primitive_db.core import (
    create_table,
    delete,
    drop_table,
    get_schema,
    insert,
    select,
    update,
    validate_clause,
    validate_table_data,
)
from primitive_db.parser import parse_command
from primitive_db.utils import (
    delete_table_data,
    get_table_path,
    load_metadata,
    load_table_data,
    save_metadata,
    save_table_data,
)


def print_help():
    """Вывести команды управления таблицами и записями."""
    print("\n***Операции с данными***")
    print("create_table <таблица> <столбец:тип> ... - создать таблицу")
    print("list_tables - показать список таблиц")
    print("drop_table <таблица> - удалить таблицу")
    print("insert into <таблица> values (<значение>, ...) - добавить запись")
    print("select from <таблица> [where <столбец> = <значение>] - выбрать записи")
    print(
        "update <таблица> set <столбец> = <значение> "
        "where <столбец> = <значение> - обновить записи"
    )
    print("delete from <таблица> where <столбец> = <значение> - удалить записи")
    print("info <таблица> - информация о таблице")
    print("help - справочная информация")
    print("exit - выйти из программы")


def execute_table_command(command, metadata):
    """Выполнить команду структуры таблиц и сохранить изменения."""
    operation = command["command"]
    if operation == "list_tables":
        if metadata:
            for table_name in metadata:
                print(f"- {table_name}")
        else:
            print("Таблиц пока нет.")
        return

    table_name = command["table_name"]
    get_table_path(table_name)

    if operation == "create_table":
        metadata = create_table(metadata, table_name, command["columns"])
        save_table_data(table_name, [])
        save_metadata(META_FILE, metadata)
        columns = ", ".join(metadata[table_name])
        print(f'Таблица "{table_name}" успешно создана со столбцами: {columns}')
    else:
        metadata = drop_table(metadata, table_name)
        save_metadata(META_FILE, metadata)
        delete_table_data(table_name)
        print(f'Таблица "{table_name}" успешно удалена.')


def print_rows(schema, rows):
    """Вывести записи в порядке столбцов схемы через PrettyTable."""
    table = PrettyTable()
    table.field_names = list(schema)
    for row in rows:
        table.add_row([row[column_name] for column_name in schema])
    print(table)


def print_info(table_name, schema, table_data):
    """Вывести имя, схему и количество записей таблицы."""
    columns = ", ".join(f"{name}:{data_type}" for name, data_type in schema.items())
    print(f"Таблица: {table_name}")
    print(f"Столбцы: {columns}")
    print(f"Количество записей: {len(table_data)}")


def execute_data_command(command, metadata):
    """Проверить схему, выполнить CRUD и сохранить успешное изменение."""
    table_name = command["table_name"]
    schema = get_schema(metadata, table_name)
    table_data = load_table_data(table_name)
    validate_table_data(schema, table_data)
    operation = command["command"]

    if operation == "info":
        print_info(table_name, schema, table_data)
        return

    if operation == "insert":
        table_data = insert(
            metadata, table_name, command["values"], table_data=table_data
        )
        save_table_data(table_name, table_data)
        print(
            f'Запись с ID={table_data[-1][ID_NAME]} успешно добавлена '
            f'в таблицу "{table_name}".'
        )
        return

    where_clause = command.get("where_clause")
    validate_clause(schema, where_clause)

    if operation == "select":
        print_rows(schema, select(table_data, where_clause))
        return

    if operation == "update":
        validate_clause(schema, command["set_clause"], allow_id=False)

    matching_rows = select(table_data, where_clause)
    if not matching_rows:
        print("Записи не найдены.")
        return

    if operation == "update":
        table_data = update(table_data, command["set_clause"], where_clause)
        save_table_data(table_name, table_data)
        for row in matching_rows:
            print(
                f'Запись с ID={row[ID_NAME]} в таблице "{table_name}" '
                "успешно обновлена."
            )
    else:
        table_data = delete(table_data, where_clause)
        save_table_data(table_name, table_data)
        for row in matching_rows:
            print(
                f'Запись с ID={row[ID_NAME]} успешно удалена '
                f'из таблицы "{table_name}".'
            )


def execute_command(command, metadata):
    """Передать разобранную команду обработчику таблиц или данных."""
    if command["command"] in ("create_table", "drop_table", "list_tables"):
        execute_table_command(command, metadata)
    else:
        execute_data_command(command, metadata)


def run():
    """Запустить цикл команд с актуальными метаданными и обработкой ошибок."""
    print_help()
    while True:
        try:
            user_input = prompt.string("Введите команду: ", empty=True).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        try:
            command = parse_command(user_input)
            if command is None:
                continue
            if command["command"] == "exit":
                break
            if command["command"] == "help":
                print_help()
                continue
            metadata = load_metadata(META_FILE)
            execute_command(command, metadata)
        except json.JSONDecodeError:
            print("Ошибка: Файл базы данных содержит некорректный JSON.")
        except ValueError as error:
            print(error)
        except KeyError as error:
            print(error.args[0])
        except OSError as error:
            print(f"Ошибка работы с файлом: {error}")
