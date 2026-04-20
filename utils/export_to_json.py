import sqlite3
import json
import re

accent_list = {'А́': 'А', 'Á': 'А', 'а́': 'а', 'á': 'а', 'Е́': 'Е', 'é': 'е', 'ё́': 'ё', 'ё́': 'ё', 'И́': 'И', 'и́': 'и', 
               'и́':'и', 'О́': 'О', 'ó': 'о', 'ý': 'У', 'у́': 'у', 'Ў': 'У', 'ў': 'у', 'Ы́': 'Ы', 
               'ы́': 'ы', 'Э́': 'Э', 'э́': 'э', 'Ю́': 'Ю', 'ю́': 'ю', 'Я́': 'Я', 'я́': 'я'}


text_example= '◊Áглицкая безрукáвка. Áглицьки безрукáвки-ти'

def clean_text(t):
    if not t:
        return ""
    text = ''
    for letter in t:          # убираем ударения
        if letter in accent_list:
            text += accent_list[letter]
        else:
            text += letter
    text = text.lower()               # в нижний регистр
    text = re.sub(r'[^а-яё\-\s]', '', text)  # оставляем только буквы (выбери свой вариант)
    text = re.sub(r'\s+', ' ', text)  # убираем лишние пробелы
    return text.strip()

print(clean_text(text_example))

# # Подключаемся к базе
conn = sqlite3.connect('dialect.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Забираем только то, что нужно
cursor.execute("""
    SELECT 
        t.id,
        t.text as content,
        t.year,
        r.name as region
    FROM Text t
    LEFT JOIN Region r ON t.region = r.id
    WHERE t.text IS NOT NULL AND t.text != ''
""")

# Превращаем в список словарей
rows = cursor.fetchall()
data = []
for row in rows:
    row_dict = dict(row)
    # Добавляем поле для Weaviate
    weaviate_item = {
        "original_id": row_dict["id"],
        "content": clean_text(row_dict["content"]),
        "year": row_dict["year"],
        "region": row_dict["region"]
    }
    data.append(weaviate_item)

# Сохраняем в JSON
with open('weaviate_export.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Сохранено {len(data)} записей в weaviate_export.json")

# Для проверки покажем первую запись
if data:
    print("\nПример первой записи:")
    print(json.dumps(data[0], ensure_ascii=False, indent=2))

conn.close()