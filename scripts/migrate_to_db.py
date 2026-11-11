import sqlite3
import json
import re
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "dialect.db"
# Путь к JSON можно переопределить аргументом: python scripts/migrate_to_db.py путь/к/тому.json
JSON_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "utils" / "парсинг словаря" / "parsed_dictionary.json"

# Лог рядом с данными (utils/ вне git, корень репозитория чистым держим)
logging.basicConfig(
    filename=str(ROOT / "utils" / "migration.log"),
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    encoding='utf-8'
)

# Токены региона в тексте словаря -> имена Region в БД (ключи — после remove_accents, т.е. lowercased)
REGION_ALIASES = {
    'шенкур.': 'шенк.',
}

# relation_type из парсера -> CHECK-совместимые значения LexicalRelation.relation_type
RELATION_TYPE_MAP = {
    'diminutive': 'diminutive_of',
    'comparative': 'derivation',
    'derived': 'derivation',
}

ACCENT_MAP = {
    'á': 'а\u0301', 'é': 'е\u0301', 'и́': 'и\u0301', 'о́': 'о\u0301',
    'ó': 'о\u0301', 'у́': 'у\u0301', 'ý': 'у\u0301', 'ў': 'у\u0306',
    'ы́': 'ы\u0301', 'э́': 'э\u0301', 'ю́': 'ю\u0301', 'я́': 'я\u0301', 'ё́': 'ё\u0301',
    'Á': 'А\u0301', 'É': 'Е\u0301', 'И́': 'И\u0301', 'О́': 'О\u0301',
    'Ó': 'О\u0301', 'У́': 'У\u0301', 'Ý': 'У\u0301', 'Ы́': 'Ы\u0301',
    'Э́': 'Э\u0301', 'Ю́': 'Ю\u0301', 'Я́': 'Я\u0301', 'Ё́': 'Ё\u0301'
}

def remove_accents(text: str) -> str:
    if not text: return ""
    text = re.sub(r'\u0301', '', text)
    for accented, replacement in ACCENT_MAP.items():
        text = text.replace(accented, replacement[0])
    return text.lower()

def resolve_region_id(region_raw, region_map):
    """Токен региона из JSON -> id Region в БД (с алиасами); None для хвоста без региона."""
    if not region_raw:
        return None
    clean = remove_accents(region_raw)
    clean = REGION_ALIASES.get(clean, clean)
    return region_map.get(clean)

def derive_pos(gram: str) -> str:
    """Грамкод словаря -> часть речи для колонки part_of_speech (фильтр /api/pos/)."""
    g = re.sub(r'\u0301', '', (gram or '').lower()).strip()
    if not g:
        return ""
    if g.startswith(("несов", "сов")):
        return "глагол"
    if g.startswith(("нареч", "нар.")):
        return "наречие"
    if re.match(r'^(ая|ее|ое|ие|ий|ой|ый)\b', g) or "прил" in g:
        return "прилагательное"
    if g.startswith(("ж", "м", "ср", "мн")) or "сущ" in g:
        return "существительное"
    return ""

# ==========================================
# ПОДГОТОВКА БАЗЫ ДАННЫХ
# ==========================================
def build_lookup_maps(cursor):
    logging.info("Построение карт поиска...")
    
    cursor.execute("SELECT id, name FROM Region")
    region_map = {remove_accents(row[1]): row[0] for row in cursor.fetchall()}

    # Теперь в БД поле word уже БЕЗ ударений, поэтому просто приводим к lower()
    cursor.execute("SELECT id, word FROM LexicalEntry")
    lexeme_map = {row[1].lower(): row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT id, name FROM Subcategory")
    subcategory_map = {remove_accents(row[1]): row[0] for row in cursor.fetchall()}

    return region_map, lexeme_map, subcategory_map

# ==========================================
# ОСНОВНАЯ МИГРАЦИЯ
# ==========================================
def migrate_data():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    region_map, lexeme_map, subcategory_map = build_lookup_maps(cursor)

    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.error(f"Файл {JSON_PATH} не найден! Проверьте путь.")
        return

    stats = {
        "lexical_entries": 0, "lexical_forms": 0, "senses": 0,
        "texts": 0, "sense_relations": 0, "lexical_relations": 0, "warnings": 0
    }

    logging.info("Начало миграции данных...")

    for subcat_data in data.get("subcategories", []):
        raw_name = subcat_data["name"]
        formatted_name = raw_name.strip().capitalize()
        clean_name = remove_accents(formatted_name)
        
        subcategory_id = subcategory_map.get(clean_name)
        if not subcategory_id:
            msg = f"Подкатегория '{formatted_name}' не найдена в БД. Блок пропущен."
            logging.warning(msg)
            stats["warnings"] += 1
            continue

        for entry_data in subcat_data["entries"]:
            # 1. LexicalEntry
            try:
                # ИЗМЕНЕНИЕ: word = без ударений, accent = с ударениями
                cursor.execute("""
                    INSERT INTO LexicalEntry (word, accent, part_of_speech, grammatical_features)
                    VALUES (?, ?, ?, ?)
                """, (
                    entry_data["word_no_accents"],
                    entry_data["word"],
                    derive_pos(entry_data.get("grammatical_features", "")),
                    entry_data.get("grammatical_features", "")
                ))
                
                lexeme_id = cursor.lastrowid
                stats["lexical_entries"] += 1
                
                # Обновляем карту поиска чистым словом
                lexeme_map[entry_data["word_no_accents"]] = lexeme_id
            except sqlite3.Error as e:
                logging.error(f"Ошибка вставки LexicalEntry '{entry_data['word']}': {e}")
                continue

            # 2. LexicalForm (вариации)
            for var in entry_data.get("variations", []):
                try:
                    # ИЗМЕНЕНИЕ: form = без ударений, accent = с ударениями
                    cursor.execute("""
                        INSERT INTO LexicalForm (lexical_entry_id, form, accent, grammatical_features)
                        VALUES (?, ?, ?, ?)
                    """, (lexeme_id, var["word_no_accents"], var["word"], var.get("grammatical_features", "")))
                    stats["lexical_forms"] += 1
                    # вариант формы может быть целью перекрёстной ссылки («То же, что подо́вый»)
                    lexeme_map[var["word_no_accents"]] = lexeme_id
                except sqlite3.Error as e:
                    logging.error(f"Ошибка вставки LexicalForm '{var['word']}': {e}")

            # 3. Sense
            for sense_idx, sense_data in enumerate(entry_data.get("senses", []), start=1):
                try:
                    cursor.execute("""
                        INSERT INTO Sense (lexical_entry_id, sense_number, meaning)
                        VALUES (?, ?, ?)
                    """, (lexeme_id, sense_idx, sense_data.get("meaning", "")))
                    
                    sense_id = cursor.lastrowid
                    stats["senses"] += 1

                    cursor.execute("""
                        INSERT INTO Sense_Subcategory (sense_id, subcategory_id)
                        VALUES (?, ?)
                    """, (sense_id, subcategory_id))

                    # 4. SenseRelation (Перекрёстные ссылки)
                    cross_ref = sense_data.get("cross_reference")
                    if cross_ref:
                        # Ищем по чистому слову
                        target_word_clean = remove_accents(cross_ref["target_word"])
                        target_lexeme_id = lexeme_map.get(target_word_clean)
                        
                        if target_lexeme_id:
                            target_sense_num = cross_ref.get("target_sense") or 1
                            cursor.execute("""
                                SELECT id FROM Sense 
                                WHERE lexical_entry_id = ? AND sense_number = ? LIMIT 1
                            """, (target_lexeme_id, target_sense_num))
                            
                            target_sense_row = cursor.fetchone()
                            target_sense_id = target_sense_row[0] if target_sense_row else None

                            if target_sense_id:
                                cursor.execute("""
                                    INSERT INTO SenseRelation (source_sense_id, target_sense_id, relation_type, status)
                                    VALUES (?, ?, 'dictionary_equivalent', 'unchecked')
                                """, (sense_id, target_sense_id))
                                stats["sense_relations"] += 1
                            else:
                                logging.warning(f"Не найден Sense #{target_sense_num} для слова '{cross_ref['target_word']}'")
                                stats["warnings"] += 1
                        else:
                            logging.warning(f"Целевое слово '{cross_ref['target_word']}' не найдено в LexicalEntry")
                            stats["warnings"] += 1

                    # 5. Text и Sense_Text (Примеры)
                    for ex in sense_data.get("examples", []):
                        region_id = resolve_region_id(ex.get("region"), region_map)

                        cursor.execute("""
                            INSERT INTO Text (text, region) VALUES (?, ?)
                        """, (ex["text"], region_id))
                        
                        text_id = cursor.lastrowid
                        stats["texts"] += 1

                        cursor.execute("""
                            INSERT INTO Sense_Text (sense_id, text_id) VALUES (?, ?)
                        """, (sense_id, text_id))

                except sqlite3.Error as e:
                    logging.error(f"Ошибка обработки Sense для '{entry_data['word']}': {e}")

            # 6. Derived Forms (Производные): форма 1 «Слово – уменьш. от …»,
            # форма 2 — статья со своей грамматикой и значениями
            for derived in entry_data.get("derived_forms", []):
                try:
                    if derived["word"] == "UNKNOWN":
                        logging.warning(f"Неразобранный блок ♦ у слова '{entry_data['word']}': "
                                        f"{derived.get('relation_description', '')[:100]}")
                        stats["warnings"] += 1
                        continue

                    cursor.execute("""
                        INSERT INTO LexicalEntry (word, accent, part_of_speech, grammatical_features)
                        VALUES (?, ?, ?, ?)
                    """, (
                        derived["word_no_accents"],
                        derived["word"],
                        derive_pos(derived.get("grammatical_features") or ""),
                        derived.get("grammatical_features") or ""
                    ))

                    derived_lexeme_id = cursor.lastrowid
                    stats["lexical_entries"] += 1
                    lexeme_map[derived["word_no_accents"]] = derived_lexeme_id

                    for var in derived.get("variations", []):
                        cursor.execute("""
                            INSERT INTO LexicalForm (lexical_entry_id, form, accent, grammatical_features)
                            VALUES (?, ?, ?, ?)
                        """, (derived_lexeme_id, var["word_no_accents"], var["word"], var.get("grammatical_features") or ""))
                        stats["lexical_forms"] += 1
                        lexeme_map[var["word_no_accents"]] = derived_lexeme_id

                    cursor.execute("""
                        INSERT INTO LexicalRelation (source_lexeme_id, target_lexeme_id, relation_type, status)
                        VALUES (?, ?, ?, 'unchecked')
                    """, (lexeme_id, derived_lexeme_id,
                          RELATION_TYPE_MAP.get(derived.get("relation_type", "derived"), 'derivation')))
                    stats["lexical_relations"] += 1

                    derived_senses = derived.get("senses") or [{
                        "meaning": derived.get("relation_description", ""),
                        "examples": derived.get("examples", []),
                    }]

                    for sense_idx, derived_sense in enumerate(derived_senses, start=1):
                        cursor.execute("""
                            INSERT INTO Sense (lexical_entry_id, sense_number, meaning)
                            VALUES (?, ?, ?)
                        """, (derived_lexeme_id, sense_idx, derived_sense.get("meaning", "")))

                        derived_sense_id = cursor.lastrowid
                        stats["senses"] += 1

                        cursor.execute("""
                            INSERT INTO Sense_Subcategory (sense_id, subcategory_id)
                            VALUES (?, ?)
                        """, (derived_sense_id, subcategory_id))

                        for ex in derived_sense.get("examples", []):
                            region_id = resolve_region_id(ex.get("region"), region_map)

                            cursor.execute("""
                                INSERT INTO Text (text, region) VALUES (?, ?)
                            """, (ex["text"], region_id))

                            text_id = cursor.lastrowid
                            stats["texts"] += 1

                            cursor.execute("""
                                INSERT INTO Sense_Text (sense_id, text_id) VALUES (?, ?)
                            """, (derived_sense_id, text_id))

                except sqlite3.Error as e:
                    logging.error(f"Ошибка обработки Derived Form '{derived['word']}': {e}")

    conn.commit()
    conn.close()

    summary = (
        f"\n✅ МИГРАЦИЯ ЗАВЕРШЕНА!\n"
        f"LexicalEntry: {stats['lexical_entries']}\n"
        f"LexicalForm: {stats['lexical_forms']}\n"
        f"Sense: {stats['senses']}\n"
        f"Text: {stats['texts']}\n"
        f"SenseRelation: {stats['sense_relations']}\n"
        f"LexicalRelation: {stats['lexical_relations']}\n"
        f"Предупреждений: {stats['warnings']}\n"
        f"Подробный лог сохранён в migration.log"
    )
    print(summary)
    logging.info(summary)

if __name__ == "__main__":
    migrate_data()