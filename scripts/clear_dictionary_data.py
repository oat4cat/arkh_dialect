# -*- coding: utf-8 -*-
"""Очистить словарные данные, сохранив структуру БД и справочники."""
import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "dialect.db"

DATA_TABLES = (
    "Concept_Sense",
    "Concept",
    "SenseRelation",
    "LexicalRelation",
    "Sense_Subcategory",
    "Sense_Text",
    "LexicalForm",
    "Sense",
    "Text",
    "LexicalEntry",
)
PRESERVED_TABLES = ("Region", "Category", "Subcategory")


def table_counts(connection: sqlite3.Connection, tables) -> dict:
    return {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }


def clear_dictionary_data(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    with connection:
        for table in DATA_TABLES:
            connection.execute(f'DELETE FROM "{table}"')

        connection.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ({})".format(
                ", ".join("?" for _ in DATA_TABLES)
            ),
            DATA_TABLES,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Удаляет лексемы, толкования, примеры, отношения и концепты. "
            "Регионы, категории и подкатегории остаются."
        )
    )
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"путь к SQLite-базе (по умолчанию: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="выполнить удаление; без этого флага показать только план",
    )
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    if not args.database.is_file():
        raise SystemExit(f"База данных не найдена: {args.database}")

    connection = sqlite3.connect(args.database)
    try:
        data_counts = table_counts(connection, DATA_TABLES)
        preserved_counts = table_counts(connection, PRESERVED_TABLES)

        print("Будет очищено:")
        for table, count in data_counts.items():
            print(f"  {table}: {count}")
        print("Справочники останутся:")
        for table, count in preserved_counts.items():
            print(f"  {table}: {count}")

        if not args.execute:
            print("\nЭто проверка без изменений. Для очистки добавьте --execute.")
            return

        clear_dictionary_data(connection)
        remaining = table_counts(connection, DATA_TABLES)
        preserved_after = table_counts(connection, PRESERVED_TABLES)
        if any(remaining.values()):
            raise RuntimeError(f"Очистка не завершена: {remaining}")
        if preserved_after != preserved_counts:
            raise RuntimeError(
                f"Справочники изменились: {preserved_counts} -> {preserved_after}"
            )
        print("\nСловарные данные очищены; структура БД и справочники сохранены.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
