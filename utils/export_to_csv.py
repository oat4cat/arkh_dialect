import sqlite3
import csv
import re

accent_list = {'А́': 'А', 'Á': 'А', 'а́': 'а', 'á': 'а', 'Е́': 'Е', 'é': 'е', 'ё́': 'ё', 'ё́': 'ё', 'И́': 'И', 'и́': 'и', 
               'и́':'и', 'О́': 'О', 'ó': 'о', 'ý': 'У', 'у́': 'у', 'Ў': 'У', 'ў': 'у', 'Ы́': 'Ы', 
               'ы́': 'ы', 'Э́': 'Э', 'э́': 'э', 'Ю́': 'Ю', 'ю́': 'ю', 'Я́': 'Я', 'я́': 'я'}

text_example = '◊Áглицкая безрукáвка. Áглицьки безрукáвки-ти'

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
    text = re.sub(r'[^а-яё.,\-–\(\)\-\s]', '', text)  # оставляем только буквы
    text = re.sub(r'\s+', ' ', text)  # убираем лишние пробелы
    return text.strip()

# Подключаемся к базе
conn = sqlite3.connect('dialect.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Забираем тексты
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

rows = cursor.fetchall()

# Для каждого текста получаем связанные слова
data = []
for row in rows:
    row_dict = dict(row)
    
    # Получаем слова для этого текста
    cursor.execute("""
        SELECT w.word, w.meaning, w.id
        FROM Word w
        JOIN Text_Word tw ON w.id = tw.word
        WHERE tw.text = ?
    """, (row_dict["id"],))
    
    words = cursor.fetchall()
    
    # Формируем строки для CSV (один текст может иметь несколько слов)
    if words:
        for word in words:
            weaviate_item = {
                "original_id": row_dict["id"],
                "content": clean_text(row_dict["content"]),
                "year": row_dict["year"] if row_dict["year"] else "",
                "region": row_dict["region"] if row_dict["region"] else "",
                "word": word["word"],
                "word_id": word["id"],
                "meaning": word["meaning"] if word["meaning"] else ""
            }
            data.append(weaviate_item)
    else:
        # Если у текста нет слов, всё равно сохраняем его
        weaviate_item = {
            "original_id": row_dict["id"],
            "content": clean_text(row_dict["content"]),
            "year": row_dict["year"] if row_dict["year"] else "",
            "region": row_dict["region"] if row_dict["region"] else "",
            "word": "",
            "word_id": "",
            "meaning": ""
        }
        data.append(weaviate_item)

# Сохраняем в CSV
if data:
    # Определяем заголовки
    fieldnames = ["original_id", "content", "year", "region", "word", "word_id", "meaning"]
    
    with open('export.csv', 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(data)
    
    print(f"Сохранено {len(data)} записей в export.csv")
    
    # Для проверки покажем первые 3 записи
    print("\nПример первых записей:")
    for i, item in enumerate(data[:3]):
        print(f"\nЗапись {i+1}:")
        for key, value in item.items():
            # Ограничиваем вывод длинных текстов
            if key == "content" and len(str(value)) > 100:
                print(f"  {key}: {value[:100]}...")
            else:
                print(f"  {key}: {value}")
else:
    print("Нет данных для экспорта")

conn.close()