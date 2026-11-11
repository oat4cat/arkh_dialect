# -*- coding: utf-8 -*-
"""Создаёт таблицы Concept и Concept_Sense в dialect.db.

DDL живёт здесь, а не в миграциях Django: модели unmanaged
(см. .kimi-code/skills/dialect-architecture/SKILL.md).
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "dialect.db"

DDL = """
CREATE TABLE IF NOT EXISTS Concept (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 0,
    forms TEXT,                 -- JSON-список форм кластера
    status TEXT NOT NULL DEFAULT 'unchecked'
        CHECK (status IN ('unchecked', 'approved', 'rejected')),
    centroid_embedding BLOB     -- средний эмбеддинг кластера (numpy bytes)
);

CREATE TABLE IF NOT EXISTS Concept_Sense (
    concept_id INTEGER NOT NULL REFERENCES Concept (id),
    sense_id INTEGER NOT NULL REFERENCES Sense (id),
    matched_form TEXT,          -- лемма-форма, давшая связь
    status TEXT NOT NULL DEFAULT 'unchecked'
        CHECK (status IN ('unchecked', 'approved', 'rejected')),
    PRIMARY KEY (concept_id, sense_id)
);

CREATE INDEX IF NOT EXISTS idx_concept_sense_sense_id ON Concept_Sense (sense_id);
"""


def main():
    con = sqlite3.connect(DB_PATH)
    con.executescript(DDL)
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
