from django.db import models
from django.db.models import CompositePrimaryKey

class Category(models.Model):
    name = models.CharField("Название категории", max_length=255, unique=True)
    description = models.TextField("Описание", blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Category'
        verbose_name = "Тематическая категория"
        verbose_name_plural = "Категории"

    def __str__(self): return self.name


class Region(models.Model):
    name = models.CharField("Название района", max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    additional = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Region'
        verbose_name = "Район (округ)"
        verbose_name_plural = "Районы"

    def __str__(self): return self.name


class Subcategory(models.Model):
    name = models.CharField("Название подкатегории", max_length=255)
    description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, db_column='category', related_name='subcategories')

    class Meta:
        managed = False
        db_table = 'Subcategory'
        unique_together = (('name', 'category'),)
        verbose_name = "Подкатегория"
        verbose_name_plural = "Подкатегории"

    def __str__(self): return self.name


class Text(models.Model):
    text = models.TextField("Текст примера")
    year = models.CharField("Год", max_length=20, blank=True, null=True)
    multimedia = models.BinaryField(blank=True, null=True)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, db_column='region', null=True, blank=True, related_name='texts')

    class Meta:
        managed = False
        db_table = 'Text'
        verbose_name = "Пример употребления"
        verbose_name_plural = "Примеры"

    def __str__(self):
        return f"{self.text[:40]}..." if self.text else "Без текста"


class LexicalEntry(models.Model):
    word = models.TextField("Слово")
    root = models.TextField("Корень", blank=True, null=True)
    part_of_speech = models.TextField("Часть речи", blank=True, null=True)
    grammatical_features = models.TextField(
        "Грамматические характеристики", blank=True, null=True
    )
    accent = models.TextField("Слово с ударением", blank=True, null=True)
    multimedia = models.BinaryField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "LexicalEntry"
        verbose_name = "Лексема"
        verbose_name_plural = "Лексемы"

    def __str__(self):
        return self.word

    @property
    def region_names(self):
        return list(
            self.senses
            .filter(texts__region__isnull=False)
            .values_list("texts__region__name", flat=True)
            .distinct()
        )


class LexicalForm(models.Model):
    lexical_entry = models.ForeignKey(
        LexicalEntry,
        on_delete=models.CASCADE,
        db_column='lexical_entry_id',
        related_name='lexical_forms',
    )
    form = models.TextField("Форма")
    accent = models.TextField("Форма с ударением", blank=True, null=True)
    grammatical_features = models.TextField(
        "Грамматические характеристики", blank=True, null=True
    )

    class Meta:
        managed = False
        db_table = 'LexicalForm'
        verbose_name = "Форма лексемы"
        verbose_name_plural = "Формы лексем"

    def __str__(self):
        return self.form


class Sense(models.Model):
    lexical_entry = models.ForeignKey(
        LexicalEntry,
        on_delete=models.CASCADE,
        db_column='lexical_entry_id',
        related_name='senses',
    )
    sense_number = models.IntegerField(blank=True, null=True)
    meaning = models.TextField(blank=True, null=True)

    texts = models.ManyToManyField(
        Text,
        through='SenseText',
        related_name='senses',
        blank=True,
    )
    subcategories = models.ManyToManyField(
        Subcategory,
        through='SenseSubcategory',
        related_name='senses',
        blank=True,
    )

    class Meta:
        managed = False
        db_table = 'Sense'
        unique_together = (('lexical_entry', 'sense_number'),)


class SenseText(models.Model):
    sense = models.ForeignKey(
        Sense, on_delete=models.CASCADE, db_column='sense_id'
    )
    text = models.ForeignKey(
        Text, on_delete=models.CASCADE, db_column='text_id'
    )
    pk = CompositePrimaryKey('sense', 'text')

    class Meta:
        managed = False
        db_table = 'Sense_Text'


class SenseSubcategory(models.Model):
    sense = models.ForeignKey(
        Sense, on_delete=models.CASCADE, db_column='sense_id'
    )
    subcategory = models.ForeignKey(
        Subcategory, on_delete=models.CASCADE, db_column='subcategory_id'
    )
    pk = CompositePrimaryKey('sense', 'subcategory')

    class Meta:
        managed = False
        db_table = 'Sense_Subcategory'


class LexicalRelation(models.Model):
    source_lexeme = models.ForeignKey(
        LexicalEntry,
        on_delete=models.CASCADE,
        db_column='source_lexeme_id',
        related_name='relations_from',
    )
    target_lexeme = models.ForeignKey(
        LexicalEntry,
        on_delete=models.CASCADE,
        db_column='target_lexeme_id',
        related_name='relations_to',
    )
    relation_type = models.CharField(max_length=30)
    status = models.CharField(max_length=20, default='unchecked')

    class Meta:
        managed = False
        db_table = 'LexicalRelation'


class SenseRelation(models.Model):
    source_sense = models.ForeignKey(
        Sense,
        on_delete=models.CASCADE,
        db_column='source_sense_id',
        related_name='relations_from',
    )
    target_sense = models.ForeignKey(
        Sense,
        on_delete=models.CASCADE,
        db_column='target_sense_id',
        related_name='relations_to',
    )
    relation_type = models.CharField(max_length=30)
    status = models.CharField(max_length=20, default='unchecked')

    class Meta:
        managed = False
        db_table = 'SenseRelation'