# -*- coding: utf-8 -*-
"""Парсер тома словаря: сырой текст -> parsed_dictionary.json.

Структура статьи в источнике (одна статья = одна строка):
    ЛЕММА (ВАРИАНТ, ...), грамматика – 1. Значение. Пример. Регион.; пример. Регион. ♦ Производное – отношение. Пример. Регион.
Дополнительные значения идут отдельными строками, начинающимися с «N. »,
и пристёгиваются к последней статье. Рубрика (подкатегория) — строка КАПСОМ,
запятые в ней возможны («ОВОЩИ, КОРНЕПЛОДЫ И ЗЕЛЕНЬ»).

Запуск:  python scripts/parse_dictionary.py [входной.txt] [выходной.json]
По умолчанию читает utils/парсинг словаря/dic3_raw.txt и пишет туда же parsed_dictionary.json.
В конце печатает сводку и список подозрительных строк — их надо просматривать глазами.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "utils" / "парсинг словаря" / "dic3_raw.txt"
DEFAULT_OUTPUT = ROOT / "utils" / "парсинг словаря" / "parsed_dictionary.json"

KNOWN_REGIONS = {'Вельск.', 'Верхнетоем.', 'Вилег.', 'Виногр.', 'Каргоп.',
                 'Кенозеро', 'Конош.', 'Котлас.', 'Красноб.', 'Ленск.',
                 'Лешук.', 'Мезен.', 'Няндом.', 'НАО.', 'Онеж.', 'Пинеж.', 'Плесец.',
                 'Примор.', 'Устьян.', 'Холмог.', 'Шенк.', 'Шенкур.'}

# Токен региона в конце строки (для производных форм после вырезания примера)
sorted_regions = sorted(KNOWN_REGIONS, key=len, reverse=True)
escaped_regions = [re.escape(r) for r in sorted_regions]
region_pattern = re.compile(r'(' + '|'.join(escaped_regions) + r')(?:\s*[;,.]?)?\s*$')

# Грамматические аббревиатуры: точку после них нельзя считать концом предложения
# («…мн., в знач. сущ. – Тонкие пироги…»). «В сочетании.» — НЕ аббревиатура.
ABBREVIATIONS = ['знач', 'сущ', 'мн', 'собир', 'одобр', 'неодобр', 'экспрес', 'груб',
                 'сов', 'несов', 'нареч', 'ср', 'ж', 'м', 'вводн', 'предик', 'перен',
                 'прям', 'безл', 'устар', 'разг', 'обл', 'диал', 'ирон', 'шутл',
                 'местоим', 'числ', 'межд', 'превосх', 'сравн', 'однокр', 'многокр',
                 'пориц', 'побуд', 'огранич', 'усил', 'сомн', 'вопр', 'эвф', 'книжн',
                 'ласк', 'пренеб', 'возвыс', 'жарг', 'уменьш', 'дет']
ABBREV_PATTERN = re.compile(r'(?<![А-ЯЁа-яё\u0301])(' + '|'.join(ABBREVIATIONS) + r')\.(?=\s)')
_DOT_GUARD = ''


def split_sentences(text: str) -> list:
    """Разбивка на предложения с защитой грамматических аббревиатур."""
    protected = ABBREV_PATTERN.sub(lambda m: m.group(1) + _DOT_GUARD, text)
    parts = re.split(r'(?<=[.!?])\s+', protected)
    return [p.replace(_DOT_GUARD, '.') for p in parts]

# Перекрёстная ссылка стоит в начале значения: «То же, что лемма (во 2-м знач.).»
cross_ref_pattern = re.compile(
    r'^(?:То же, что|Ср\.|См\.)\s+([а-яёА-ЯЁ\u0301\-]+)'
    r'(?:\s*\(во?\s*(\d+)[\-\s]?м?\s*знач\.?\))?',
    re.IGNORECASE,
)

# Блок производной формы после ♦, форма 1: «Воло́жка – уменьш. от воло́га. Пример. Регион.»
# (варианты в скобках возможны: «Еру́шничек (яру́шничек) – …»).
# Пример начинается с заглавной/кавычки — иначе «от воло́га.» утекало из описания отношения в пример.
derived_form_pattern = re.compile(
    r'^([А-ЯЁ][а-яё\u0301]+)(?:\s*\(([^)]+)\))?\s*[–-]\s*(.*?)\.\s+([А-ЯЁ«"(].*)'
)

# Рубрика: только заглавные кириллические, пробелы и запятые («ГРИБЫ», «МЯСО, САЛО И БЛЮДА ИЗ НИХ»).
# Статья не матчится сюда: в ней после запятой идёт строчная грамматика (ж., м., ср. ...).
re_subcategory = re.compile(r'^([А-ЯЁ][А-ЯЁ\s,]{2,})$')

# Производная форма-статья после ♦: лемма строго одно слово, затем грамматика до тире.
# Отличается от re_entry нежадностью леммы: не съедает « – уменьш. от …» как часть слова.
derived_entry_pattern = re.compile(
    r'^([А-ЯЁ][а-яё\u0301]+)'
    r'(?:\s*\(([^)]+)\))?'
    r'\s*,\s*'
    r'(.+?)'
    r'\s+[–-]\s*'
    r'(.*)$'
)

# Статья: ЛЕММА, грамблок – остальное. Слово — от начала строки до запятой/скобки,
# грамблок — нежадно до « – », дальше — значения и примеры.
re_entry = re.compile(
    r'^([А-ЯЁA-Z\u00C0-\u00DE][^,(]*)'
    r'(?:\s*\(([^)]+)\))?'
    r'\s*,\s*'
    r'(.+?)'
    r'\s+[–-]\s*'                                  # Тире-разделитель; пробел после может отсутствовать («ж. –То же»)
    r'(.*)$'
)

# ============ АКЦЕНТЫ ============
# В источнике ударение — комбинируемый акут (а + U+0301) и латинские копии с акутом (É).
ACCENT_MAP = {
    'á': 'а\u0301', 'é': 'е\u0301', 'и́': 'и\u0301', 'о́': 'о\u0301',
    'ó': 'о\u0301', 'у́': 'у\u0301', 'ý': 'у\u0301', 'ў': 'у\u0306',
    'ы́': 'ы\u0301', 'э́': 'э\u0301', 'ю́': 'ю\u0301', 'я́': 'я\u0301', 'ё́': 'ё\u0301',
    'Á': 'А\u0301', 'É': 'Е\u0301', 'И́': 'И\u0301', 'О́': 'О\u0301',
    'Ó': 'О\u0301', 'У́': 'У\u0301', 'Ý': 'У\u0301', 'Ы́': 'Ы\u0301',
    'Э́': 'Э\u0301', 'Ю́': 'Ю\u0301', 'Я́': 'Я\u0301', 'Ё́': 'Ё\u0301'
}


def normalize_accents(text: str) -> str:
    """Латинские копии с акутом -> кириллица с комбинируемым акутом."""
    for accented, replacement in ACCENT_MAP.items():
        text = text.replace(accented, replacement)
    return text


def remove_accents(text: str) -> str:
    """Убрать все акценты, результат в нижнем регистре."""
    text = re.sub(r'\u0301', '', text)
    for accented, replacement in ACCENT_MAP.items():
        text = text.replace(accented, replacement[0])
    return text.lower()


# ============ ПАРСИНГ ============
def parse_examples(text: str) -> list:
    """Примеры — это цепочки предложений, завершающиеся токеном региона.
    «;» разделяет разные регионы, «//» — варианты одного региона, поэтому
    ВСЕ предложения чанка наследуют его регион; хвост без региона — region=None.
    """
    normalized = text.replace('//', '. ')
    region_token = re.compile(r'(' + '|'.join(escaped_regions) + r')(?:\s*;)?')

    def sentences(chunk: str, region):
        for sent in split_sentences(chunk):
            sent = re.sub(r'^[.\s]+', '', sent.strip())
            if sent and re.search(r'[А-ЯЁа-яё]', sent):
                examples.append({"text": normalize_accents(sent), "region": region})

    examples = []
    pos = 0
    for m in region_token.finditer(normalized):
        sentences(normalized[pos:m.start()], m.group(1))
        pos = m.end()
    sentences(normalized[pos:], None)
    return examples


def parse_senses(text: str) -> list:
    """Нумерованный список значений: первое предложение — толкование,
    перекрёстная ссылка «То же, что …» уходит в cross_reference."""
    senses = []
    for part in re.split(r'(?=\d+\.\s)', text.strip()):
        part = part.strip()
        if not part:
            continue

        sense_text = re.sub(r'^\d+\.\s*', '', part)
        sense_data = {"meaning": "", "cross_reference": None, "examples": []}

        cr = cross_ref_pattern.match(sense_text)
        if cr:
            sense_data["cross_reference"] = {
                "target_word": normalize_accents(cr.group(1).strip()).lower(),
                "target_sense": int(cr.group(2)) if cr.group(2) else None,
            }
            sense_data["meaning"] = cr.group(0).strip().rstrip('.') + "."
            remainder = re.sub(r'^[\.\s]+', '', sense_text[cr.end():])
            sense_data["examples"] = parse_examples(remainder)
        else:
            sentences = split_sentences(sense_text)
            sense_data["meaning"] = normalize_accents(sentences[0].strip())
            sense_data["examples"] = parse_examples(' '.join(sentences[1:]))

        senses.append(sense_data)
    return senses


def make_variations(variations_raw: str, var_gram_raw: str) -> list:
    variations = []
    if variations_raw:
        for vw in variations_raw.split(','):
            vw = vw.strip()
            variations.append({
                "word": normalize_accents(vw).lower(),
                "word_no_accents": remove_accents(vw),
                "grammatical_features": normalize_accents(var_gram_raw) if var_gram_raw else None
            })
    return variations


def split_gram_block(gram_block_raw: str):
    """«ая, ое (а́я, о́е)» -> («ая, ое», «а́я, о́е») — грамматика основная и для вариантов."""
    main_gram = gram_block_raw
    var_gram_raw = ""
    if '(' in gram_block_raw and ')' in gram_block_raw:
        parts = gram_block_raw.split('(', 1)
        main_gram = parts[0].strip().rstrip(',')
        var_gram_raw = parts[1].replace(')', '').strip()
    return main_gram, var_gram_raw


def relation_type_of(description: str) -> str:
    d = description.lower()
    if "уменьш" in d:
        return "diminutive"
    if "сравн" in d:
        return "comparative"
    return "derived"


def process_senses(text: str, entry: dict) -> None:
    parts_with_diamond = text.split('♦')

    # extend: статья может занимать несколько строк (доп. значения «N. …» пристёгиваются)
    entry["senses"].extend(parse_senses(parts_with_diamond[0]))

    for block in parts_with_diamond[1:]:
        block = block.strip()
        if not block:
            continue

        # Форма 2: после ♦ — полноценная статья со своей грамматикой:
        # «♦ Нескусня́щий, экспрес., неодобр. – Очень невкусный. Пример. Регион.»
        # Лемма строго одно слово: без этого «Колобо́к – уменьш. от …» с запятой
        # в примерах улетал сюда вместо формы 1.
        m_entry = derived_entry_pattern.match(block)
        if m_entry:
            main_gram, var_gram_raw = split_gram_block(m_entry.group(3).strip())
            entry["derived_forms"].append({
                "word": normalize_accents(m_entry.group(1).strip()).lower(),
                "word_no_accents": remove_accents(m_entry.group(1).strip()),
                "variations": make_variations(m_entry.group(2), var_gram_raw),
                "grammatical_features": normalize_accents(main_gram),
                "relation_type": "derived",
                "relation_description": "",
                "senses": parse_senses(m_entry.group(4).strip()),
                "examples": [],
            })
            continue

        # Форма 1: «Производное – отношение. Пример. Регион.»
        m_der = derived_form_pattern.match(block)
        if not m_der:
            entry["derived_forms"].append({
                "word": "UNKNOWN", "word_no_accents": "unknown",
                "relation_type": "unparsed",
                "relation_description": normalize_accents(block),
                "examples": [],
            })
            continue

        new_word, var_raw, relation_desc, example_text = m_der.groups()

        region = None
        rm = region_pattern.search(example_text)
        if rm:
            region = rm.group(1)
            example_text = region_pattern.sub('', example_text).strip().rstrip('.!?')

        entry["derived_forms"].append({
            "word": normalize_accents(new_word).lower(),
            "word_no_accents": remove_accents(new_word),
            "variations": make_variations(var_raw, ""),
            "grammatical_features": None,
            "relation_type": relation_type_of(relation_desc),
            "relation_description": normalize_accents(relation_desc),
            "senses": [],
            "examples": [{"text": normalize_accents(example_text), "region": region}]
                        if example_text else [],
        })


def parse_dictionary_text(text: str) -> dict:
    # Латинские копии с акутом (ó, É) ломают строгие классы regex — нормализуем весь текст сразу
    text = normalize_accents(text)

    result = {"subcategories": []}
    current_subcategory = None
    current_entry = None
    suspicious = []

    for line_num, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue

        if re_subcategory.match(line):
            current_subcategory = {"name": line.strip(), "entries": []}
            result["subcategories"].append(current_subcategory)
            current_entry = None
            continue

        m = re_entry.match(line)
        if m:
            word_raw = m.group(1).strip()
            main_gram, var_gram_raw = split_gram_block(m.group(3).strip())
            rest = m.group(4).strip()
            variations = make_variations(m.group(2), var_gram_raw)

            current_entry = {
                "word": normalize_accents(word_raw).lower(),
                "word_no_accents": remove_accents(word_raw),
                "variations": variations,
                "grammatical_features": normalize_accents(main_gram),
                "senses": [],
                "derived_forms": [],
            }
            if current_subcategory is not None:
                current_subcategory["entries"].append(current_entry)
            else:
                suspicious.append((line_num, 'статья вне рубрики', line[:80]))
            process_senses(rest, current_entry)
            continue

        if current_entry is not None:
            # Строка не распознана как статья: легальное продолжение начинается с «N. »
            if not re.match(r'^\d+\.\s', line):
                suspicious.append((line_num, 'не статья и не продолжение', line[:80]))
            process_senses(line, current_entry)
        else:
            suspicious.append((line_num, 'сирота вне статьи', line[:80]))

    result["_suspicious"] = suspicious
    return result


def print_report(data: dict) -> None:
    subcats = data["subcategories"]
    entries = [e for s in subcats for e in s["entries"]]
    senses = [sense for e in entries for sense in e["senses"]]
    examples = [ex for sense in senses for ex in sense["examples"]]
    derived = [d for e in entries for d in e["derived_forms"]]
    print(f"Рубрик: {len(subcats)} | Статей: {len(entries)} | Значений: {len(senses)} "
          f"| Примеров: {len(examples)} (без региона: {sum(1 for ex in examples if ex['region'] is None)}) "
          f"| Производных: {len(derived)} (UNKNOWN: {sum(1 for d in derived if d['word'] == 'UNKNOWN')})")
    for s in subcats:
        print(f"  {s['name'].capitalize()}: {len(s['entries'])} статей")
    suspicious = data.get("_suspicious", [])
    if suspicious:
        print(f"\n=== ПОДОЗРИТЕЛЬНЫЕ СТРОКИ: {len(suspicious)} (просмотреть глазами) ===")
        for line_num, kind, preview in suspicious:
            print(f"  стр.{line_num} [{kind}]: {preview}")


def main() -> None:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT

    text = input_path.read_text(encoding='utf-8-sig')
    parsed_data = parse_dictionary_text(text)
    suspicious = parsed_data.pop("_suspicious", [])

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, ensure_ascii=False, indent=2)

    print(f"Записано: {output_path}")
    parsed_data["_suspicious"] = suspicious
    print_report(parsed_data)


if __name__ == "__main__":
    main()
