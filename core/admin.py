from django.contrib import admin
from .models import Word, Region, Subcategory, Category, Text, WordHomonyms, WordSynonyms

# --- Словарные статьи ---
@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ('word', 'accent', 'part_of_speech', 'get_regions_list')
    list_filter = ('part_of_speech', 'subcategories')
    search_fields = ('word', 'accent', 'meaning')
    
    def get_regions_list(self, obj):
        # Безопасный запрос через промежуточную таблицу
        regs = obj.textwords.values_list('text__region__name', flat=True).distinct()
        return ", ".join(regs[:3]) + ("..." if len(regs) > 3 else "")
    get_regions_list.short_description = "Районы"

# --- Регионы ---
@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)

# --- Категории и подкатегории ---
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class SubcategoryInline(admin.TabularInline):
    model = Subcategory
    extra = 1

@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    list_filter = ('category',)
    search_fields = ('name',)

# --- Примеры употребления ---
@admin.register(Text)
class TextAdmin(admin.ModelAdmin):
    list_display = ('text_short', 'region', 'year')
    list_filter = ('region',)
    search_fields = ('text',)
    
    def text_short(self, obj):
        return obj.text[:60] + "..." if len(obj.text) > 60 else obj.text
    text_short.short_description = "Текст примера"

# --- Омонимы и Синонимы (фиксируем AttributeError) ---
@admin.register(WordHomonyms)
class WordHomonymsAdmin(admin.ModelAdmin):
    list_display = ('word', 'word_2')
    list_filter = ('word__part_of_speech',)
    search_fields = ('word__word', 'word_2__word')
    autocomplete_fields = ('word_2',)  # word уже является pk, его не трогаем

@admin.register(WordSynonyms)
class WordSynonymsAdmin(admin.ModelAdmin):
    list_display = ('word', 'word_2')
    list_filter = ('word__part_of_speech',)
    search_fields = ('word__word', 'word_2__word')
    autocomplete_fields = ('word_2',)