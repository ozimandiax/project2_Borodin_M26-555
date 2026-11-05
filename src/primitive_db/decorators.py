"""Обрабатывать ошибки, подтверждать действия и кэшировать результаты."""

import json
import time

from primitive_db.constants import ACTION_CANCELLED, DB_ERROR

_error_handler_depth = [0]


def _preserve_metadata(wrapper, wrapped):
    """Сохранить имя, документацию и ссылку на исходную функцию."""
    wrapper.__name__ = wrapped.__name__
    wrapper.__doc__ = wrapped.__doc__
    wrapper.__module__ = wrapped.__module__
    wrapper.__qualname__ = wrapped.__qualname__
    wrapper.__wrapped__ = wrapped
    return wrapper


def _error_message(error):
    """Подготовить одно понятное сообщение об ошибке базы данных."""
    if isinstance(error, json.JSONDecodeError):
        return "Ошибка: Файл данных содержит некорректный JSON."
    if isinstance(error, FileNotFoundError):
        return (
            "Ошибка: Файл данных не найден. "
            "Возможно, база данных не инициализирована."
        )
    if isinstance(error, KeyError):
        missing_name = error.args[0] if error.args else "неизвестное имя"
        if isinstance(missing_name, str) and missing_name.startswith("Ошибка:"):
            return missing_name
        return f"Ошибка: Таблица или столбец {missing_name!r} не найден."
    if isinstance(error, ValueError):
        message = str(error)
        if message.startswith(("Ошибка", "Некоррект", "Функции ")):
            return message
        return f"Ошибка валидации: {message or 'некорректные данные'}"
    if isinstance(error, OSError):
        return f"Ошибка работы с файлом: {error}"
    return f"Произошла непредвиденная ошибка: {error}"


def handle_db_errors(func):
    """Перехватить ошибку только на внешнем уровне вызовов декоратора."""
    def wrapper(*args, **kwargs):
        """Обработать ошибку на внешнем уровне и восстановить глубину."""
        outermost = _error_handler_depth[0] == 0
        _error_handler_depth[0] += 1
        try:
            return func(*args, **kwargs)
        except Exception as error:
            if not outermost:
                raise
            print(_error_message(error))
            return DB_ERROR
        finally:
            _error_handler_depth[0] -= 1

    return _preserve_metadata(wrapper, func)


def confirm_action(action_name):
    """Создать декоратор, требующий подтверждения опасной операции."""
    def decorator(func):
        """Добавить запрос подтверждения к переданной функции."""
        def wrapper(*args, **kwargs):
            """Выполнить функцию только после явного подтверждения."""
            try:
                answer = input(
                    f'Вы уверены, что хотите выполнить "{action_name}"? [y/n]: '
                ).strip()
            except (EOFError, KeyboardInterrupt):
                answer = ""

            if answer != "y":
                print("Операция отменена.")
                return ACTION_CANCELLED
            return func(*args, **kwargs)

        return _preserve_metadata(wrapper, func)

    return decorator


def log_time(func):
    """Вывести время выполнения функции, включая ошибочный вызов."""
    def wrapper(*args, **kwargs):
        """Измерить вызов и вывести время даже при исключении."""
        started_at = time.monotonic()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.monotonic() - started_at
            print(
                f"Функция {func.__name__} выполнилась за {elapsed:.3f} секунд."
            )

    return _preserve_metadata(wrapper, func)


def create_cacher():
    """Создать функцию кэширования со словарём в замыкании."""
    cache = {}

    def cache_result(key, value_func):
        """Вернуть сохранённый результат или вычислить успешное значение."""
        if key in cache:
            return cache[key]
        result = value_func()
        if result is not DB_ERROR and result is not ACTION_CANCELLED:
            cache[key] = result
        return result

    return cache_result
