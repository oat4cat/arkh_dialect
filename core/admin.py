from django.contrib import admin

from .models import (
    Category,
    LexicalEntry,
    LexicalRelation,
    Region,
    Sense,
    SenseRelation,
    Subcategory,
    Text,
)


class SenseInline(admin.TabularInline):
    model = Sense
    extra = 0
    fields = ("sense_number", "meaning")


class LexicalRelationInline(admin.TabularInline):
    model = LexicalRelation
    fk_name = "source_lexeme"
    extra = 0
    fields = ("target_lexeme", "relation_type", "status")
    autocomplete_fields = ("target_lexeme",)


class SenseRelationInline(admin.TabularInline):
    model = SenseRelation
    fk_name = "source_sense"
    extra = 0
    fields = ("target_sense", "relation_type", "status")
    autocomplete_fields = ("target_sense",)


@admin.register(LexicalEntry)
class LexicalEntryAdmin(admin.ModelAdmin):
    list_display = ("word", "accent", "part_of_speech", "get_regions_list")
    list_filter = ("part_of_speech",)
    search_fields = ("word", "accent", "senses__meaning")
    inlines = (SenseInline, LexicalRelationInline)

    @admin.display(description="Районы")
    def get_regions_list(self, obj):
        regions = (
            obj.texts.filter(region__isnull=False)
            .values_list("region__name", flat=True)
            .distinct()
        )
        names = list(regions[:4])
        return ", ".join(names[:3]) + ("..." if len(names) > 3 else "")


@admin.register(Sense)
class SenseAdmin(admin.ModelAdmin):
    list_display = ("lexical_entry", "sense_number", "meaning")
    search_fields = ("lexical_entry__word", "meaning")
    inlines = (SenseRelationInline,)


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

    @admin.display(description="Текст примера")
    def text_short(self, obj):
        return obj.text[:60] + ("..." if len(obj.text) > 60 else "")