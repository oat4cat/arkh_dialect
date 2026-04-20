import weaviate
from weaviate.classes.config import Configure, Property, DataType
import json
import uuid

try:
    # Подключаемся
    client = weaviate.connect_to_local()
    print(client.is_ready())
    # Проверяем и создаём схему
    if not client.collections.exists("DialectText"):
        client.collections.create(
            name="DialectText",
            properties=[
                Property(name="original_id", data_type=DataType.INT),
                Property(name="content", data_type=DataType.TEXT),
                Property(name="year", data_type=DataType.TEXT),
                Property(name="region", data_type=DataType.TEXT),
            ]
        )
        print("Создан класс DialectText")
    
    # Читаем JSON
    with open('weaviate_export_ready.json', 'r', encoding='utf-8') as f:
        items = json.load(f)
    
    # Получаем коллекцию
    collection = client.collections.get("DialectText")
    
    # Загружаем данные
    for item in items:
        collection.data.insert(
            properties=item,
            uuid=uuid.uuid5(uuid.NAMESPACE_DNS, str(item["original_id"]))
        )
        print(f"Загружено: {item['original_id']}")
    
    print(f"Всего загружено: {len(items)} записей")
    client.close()
    
except Exception as e:
    print(f"Ошибка: {e}")
    client.close()

finally:
    if 'client' in locals():
        client.close()
        print("Соединение закрыто")