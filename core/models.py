from django.db import models
from django.db.models import CompositePrimaryKey

class Category(models.Model):
    name = models.CharField("Название категории", max_length=255, unique=True)
    description = models.TextField("Описание", blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Category'
        verbose_name_plural = "Категории"

    def __str__(self): return self.name


class Region(models.Model):
    name = models.CharField("Название района", max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    additional = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Region'

    def __str__(self): return self.name


class Subcategory(models.Model):
    name = models.CharField("Название подкатегории", max_length=255)
    description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, db_column='category', related_name='subcategories')

    class Meta:
        managed = False
        db_table = 'Subcategory'
        unique_together = (('name', 'category'),)

    def __str__(self): return self.name


class Word(models.Model):
    word = models.CharField("Слово", max_length=255)
    meaning = models.TextField("Значение", blank=True, null=True)
    root = models.CharField("Корень", max_length=255, blank=True, null=True)
    part_of_speech = models.CharField("Часть речи", max_length=100, blank=True, null=True)
    grammatical_features = models.CharField("Грамматические характеристики", max_length=255, blank=True, null=True)
    accent = models.CharField("Слово с ударением", max_length=255, blank=True, null=True)
    multimedia = models.BinaryField(blank=True, null=True)


    subcategories = models.ManyToManyField(Subcategory, through='SubcategoryWord', related_name='words', blank=True)
 
    class Meta:
        managed = False
        db_table = 'Word'

    def __str__(self): return self.word

    @property
    def region_names(self):
        return list(
            self.text_set.values_list('region__name', flat=True)
            .distinct()
            .exclude(region__isnull=True)
        )


class SubcategoryWord(models.Model):
    subcategory = models.ForeignKey(Subcategory, on_delete=models.CASCADE, db_column='subcategory', related_name='subcategorywords')
    word = models.ForeignKey(Word, on_delete=models.CASCADE, db_column='word', related_name='subcategorywords')
    # Составной ключ, точно как в вашей БД
    pk = CompositePrimaryKey('subcategory', 'word')

    class Meta:
        managed = False
        db_table = 'Subcategory_Word'
        

class Text(models.Model):
    text = models.TextField("Текст примера")
    year = models.CharField("Год", max_length=20, blank=True, null=True)
    multimedia = models.BinaryField(blank=True, null=True)
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, db_column='region', null=True, blank=True, related_name='texts')

    class Meta:
        managed = False
        db_table = 'Text'

    def __str__(self):
        return f"{self.text[:40]}..." if self.text else "Без текста"


class TextWord(models.Model):
    text = models.ForeignKey(Text, on_delete=models.CASCADE, db_column='text', related_name='textwords')
    word = models.ForeignKey(Word, on_delete=models.CASCADE, db_column='word', related_name='textwords')
    pk = CompositePrimaryKey('text', 'word')

    class Meta:
        managed = False
        db_table = 'Text_Word'


class WordHomonyms(models.Model):
    id = models.AutoField(primary_key=True)
    word = models.ForeignKey(Word, on_delete=models.CASCADE, db_column='word', related_name='homonyms_from')
    word_2 = models.ForeignKey(Word, on_delete=models.CASCADE, db_column='word_2', related_name='homonyms_to')

    class Meta:
        managed = False
        db_table = 'Word_homonyms'
        unique_together = ('word', 'word_2')


class WordSynonyms(models.Model):
    id = models.AutoField(primary_key=True)
    word = models.ForeignKey(Word, on_delete=models.CASCADE, db_column='word', related_name='synonyms_from')
    word_2 = models.ForeignKey(Word, on_delete=models.CASCADE, db_column='word_2', related_name='synonyms_to')

    class Meta:
        managed = False
        db_table = 'Word_synonyms'
        unique_together = ('word', 'word_2')