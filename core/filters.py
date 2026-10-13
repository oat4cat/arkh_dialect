# core/filters.py
import django_filters
from django.db.models import Q
from .models import LexicalEntry, Subcategory, Region

class LexicalEntryFilter(django_filters.FilterSet):
    # Поиск по слову (регистронезависимый, частичное совпадение)
    word = django_filters.CharFilter(method='filter_word')

    def filter_word(self, queryset, name, value):
        return queryset.filter(
            Q(word__icontains=value) | Q(lexical_forms__form__icontains=value)
        ).distinct()
    
    # Фильтр по подкатегориям (множественный выбор)
    subcategories = django_filters.ModelMultipleChoiceFilter(
        field_name='senses__subcategories__name',
        queryset=Subcategory.objects.all(),
        to_field_name='name'
    )
    
    # Фильтр по регионам (через Sense → Text → Region)
    regions = django_filters.ModelMultipleChoiceFilter(
        field_name='senses__texts__region__name',
        queryset=Region.objects.all(),
        to_field_name='name'
    )
    
    # Фильтр по частям речи
    part_of_speech = django_filters.MultipleChoiceFilter(
        field_name='part_of_speech',
        choices=lambda: LexicalEntry.objects.values_list('part_of_speech', 'part_of_speech')
                              .distinct()
                              .exclude(part_of_speech__isnull=True)
                              .exclude(part_of_speech=''),
    )
    
    class Meta:
        model = LexicalEntry
        fields = ['word', 'subcategories', 'regions', 'part_of_speech']