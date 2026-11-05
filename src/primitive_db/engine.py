import prompt


def print_help():
    """Вывести список доступных команд."""
    print("<command> exit - выйти из программы")
    print("<command> help - справочная информация")


def welcome():
    """Запустить цикл обработки команд пользователя."""
    print("Первая попытка запустить проект!")
    print("\n***")
    print_help()

    while True:
        command = prompt.string("Введите команду: ").strip()

        if command == "exit":
            break
        elif command == "help":
            print_help()
        else:
            print(f"Функции {command} нет. Попробуйте снова.")
