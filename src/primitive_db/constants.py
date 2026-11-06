META_FILE = "db_meta.json"
DATA_DIR = "data"
JSON_ENCODING = "utf-8"
JSON_INDENT = 4
TEMP_FILE_TOKEN_BYTES = 8
TEMP_FILE_MODE = 0o600
TEMP_FILE_PREFIX = ".primitive-db-"
TEMP_FILE_SUFFIX = ".tmp"
FILE_COPY_CHUNK_SIZE = 64 * 1024
TABLE_FILE_EXTENSION = ".json"
CONTROL_CHARACTER_LIMIT = 32
VALID_TYPES = ("int", "str", "bool")
TYPE_CLASSES = {"int": int, "str": str, "bool": bool}
ID_NAME = "ID"
ID_COLUMN = "ID:int"

DB_ERROR = object()
ACTION_CANCELLED = object()

TOKEN_SYMBOL = "symbol"
TOKEN_QUOTED = "quoted"
TOKEN_MIXED = "mixed"
TOKEN_WORD = "word"
TOKEN_PUNCTUATION = "(),="
DOUBLE_QUOTE = '"'
QUOTE_CHARACTERS = (DOUBLE_QUOTE, "'")
BOOLEAN_LITERALS = {"true": True, "false": False}

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
