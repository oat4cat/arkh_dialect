from django.contrib import admin

from .models import (
    Category,
    LexicalEntry,
    LexicalForm,
    LexicalRelation,
    Region,
    Sense,
    SenseRelation,
    SenseText,
    Subcategory,
    Text,
)


class SenseInline(admin.TabularInline):
    model = Sense
    extra = 0
    fields = ("sense_number", "meaning")
    verbose_name = "смысл"
    verbose_name_plural = "Смыслы"


class LexicalFormInline(admin.TabularInline):
    model = LexicalForm
    extra = 0
    fields = ("form", "accent", "grammatical_features")
    verbose_name = "форма лексемы"
    verbose_name_plural = "Формы лексемы"


class LexicalRelationInline(admin.TabularInline):
    model = LexicalRelation
    fk_name = "source_lexeme"
    extra = 0
    fields = ("target_lexeme", "relation_type", "status")
    autocomplete_fields = ("target_lexeme",)
    verbose_name = "связь лексемы"
    verbose_name_plural = "Связи лексемы"


class SenseRelationInline(admin.TabularInline):
    model = SenseRelation
    fk_name = "source_sense"
    extra = 0
    fields = ("target_sense", "relation_type", "status")
    autocomplete_fields = ("target_sense",)
    verbose_name = "связь смысла"
    verbose_name_plural = "Связи смысла"


class SenseTextInline(admin.TabularInline):
    model = SenseText
    extra = 0
    fields = ("text",)
    autocomplete_fields = ("text",)
    verbose_name = "пример употребления"
    verbose_name_plural = "Примеры употребления"


class TextSenseInline(admin.TabularInline):
    model = SenseText
    extra = 0
    fields = ("sense",)
    autocomplete_fields = ("sense",)
    verbose_name = "смысл"
    verbose_name_plural = "Связанные смыслы"


@admin.register(LexicalEntry)
class LexicalEntryAdmin(admin.ModelAdmin):
    list_display = ("word", "accent", "part_of_speech", "get_regions_list")
    list_filter = ("part_of_speech",)
    search_fields = ("word", "accent", "senses__meaning")
    inlines = (LexicalFormInline, SenseInline, LexicalRelationInline)

    @admin.display(description="Районы")
    def get_regions_list(self, obj):
        regions = (
            obj.senses.filter(texts__region__isnull=False)
            .values_list("texts__region__name", flat=True)
            .distinct()
        )
        names = list(regions[:4])
        return ", ".join(names[:3]) + ("..." if len(names) > 3 else "")


@admin.register(Sense)
class SenseAdmin(admin.ModelAdmin):
    list_display = ("lexical_entry", "sense_number", "meaning")
    search_fields = ("lexical_entry__word", "meaning")
    inlines = (SenseTextInline, SenseRelationInline)


@admin.register(LexicalRelation)
class LexicalRelationAdmin(admin.ModelAdmin):
    list_display = (
        "source_lexeme",
        "target_lexeme",
        "relation_type",
        "status",
    )
    list_filter = ("relation_type", "status")
    search_fields = ("source_lexeme__word", "target_lexeme__word")
    autocomplete_fields = ("source_lexeme", "target_lexeme")


@admin.register(SenseRelation)
class SenseRelationAdmin(admin.ModelAdmin):
    list_display = (
        "source_sense",
        "target_sense",
        "relation_type",
        "status",
    )
    list_filter = ("relation_type", "status")
    search_fields = (
        "source_sense__lexical_entry__word",
        "target_sense__lexical_entry__word",
    )
    autocomplete_fields = ("source_sense", "target_sense")


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name", "category__name")


@admin.register(Text)
class TextAdmin(admin.ModelAdmin):
    list_display = ("text_short", "region", "year")
    list_filter = ("region",)
    search_fields = ("text",)
    inlines = (TextSenseInline,)

    @admin.display(description="Текст примера")
    def text_short(self, obj):
        return obj.text[:60] + ("..." if len(obj.text) > 60 else "")