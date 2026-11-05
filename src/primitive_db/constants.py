META_FILE = "db_meta.json"
DATA_DIR = "data"
VALID_TYPES = ("int", "str", "bool")
TYPE_CLASSES = {"int": int, "str": str, "bool": bool}
ID_NAME = "ID"
ID_COLUMN = "ID:int"

TABLE_INVALID_CHARACTERS = r'<>:"/\|?*'
TABLE_RESERVED_NAMES = (
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
)

COMMANDS = (
    "create_table",
    "drop_table",
    "list_tables",
    "insert",
    "select",
    "update",
    "delete",
    "info",
    "help",
    "exit",
)
