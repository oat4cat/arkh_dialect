# core/filters.py
import django_filters
from .models import LexicalEntry, Subcategory, Region

class LexicalEntryFilter(django_filters.FilterSet):
    # Поиск по слову (регистронезависимый, частичное совпадение)
    word = django_filters.CharFilter(lookup_expr='icontains', field_name='word')
    
    # Фильтр по подкатегориям (множественный выбор)
    subcategories = django_filters.ModelMultipleChoiceFilter(
        field_name='subcategories__name',
        queryset=Subcategory.objects.all(),
        to_field_name='name'
    )
    
    # Фильтр по регионам (через Text → Region)
    regions = django_filters.ModelMultipleChoiceFilter(
        field_name='texts__region__name', 
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