import json


def load_metadata(filepath):
    """Загрузить метаданные или вернуть пустой словарь."""
    try:
        with open(filepath, encoding="utf-8") as metadata_file:
            return json.load(metadata_file)
    except FileNotFoundError:
        return {}


def save_metadata(filepath, data):
    """Сохранить метаданные в JSON-файл."""
    with open(filepath, "w", encoding="utf-8") as metadata_file:
        json.dump(data, metadata_file, ensure_ascii=False, indent=4)
