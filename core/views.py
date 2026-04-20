# core/views.py
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator
from .filters import WordFilter  
from .models import Region, Subcategory, Category, Word


@require_POST
def search_api(request):
    """Замена results.php — с django-filter"""
    data = json.loads(request.body)
    
    # Получаем базовый QuerySet
    qs = Word.objects.select_related().prefetch_related(
        'subcategories',
        'textwords__text__region'
    )
    
    # Применяем фильтр django-filter
    word_filter = WordFilter(data={
        'word': data.get('word', ''),
        'subcategories': data.get('subcategories', []),
        'regions': data.get('regions', []),
        'part_of_speech': data.get('pos', []), 
    }, queryset=qs)
    
    # Получаем отфильтрованный QuerySet
    filtered_qs = word_filter.qs
    
    # Сортировка 
    order = int(data.get('order', 0))
    order_map = {0: 'word', 1: '-word', 2: 'subcategories__name', 3: '-subcategories__name'}
    filtered_qs = filtered_qs.order_by(order_map.get(order, 'word'))
    
    # Пагинация
    paginator = Paginator(filtered_qs, 20)
    page_obj = paginator.get_page(int(data.get('page', 1)))
    
    # Сериализация результатов
    results = []
    for w in page_obj:

        examples = []
        region_names = set()

        # Получаем выбранные регионы из запроса (если есть)
        selected_regions = set(data.get('regions', []))

        for tw in w.textwords.all():
            text_obj = tw.text
            region_name = text_obj.region.name if text_obj.region else None
            
            # Если регионы выбраны — показываем только примеры из них
            if selected_regions:
                if region_name and region_name in selected_regions:
                    examples.append({
                        'text': text_obj.text,
                        'region': region_name
                    })
                    region_names.add(region_name)
            # Если регионы не выбраны — показываем все примеры
            else:
                if region_name:
                    region_names.add(region_name)
                examples.append({
                    'text': text_obj.text,
                    'region': region_name
                })

        # Добавляем слово в результаты только если есть примеры 
        if not examples and selected_regions:
            continue  # Пропускаем слово, если нет примеров в выбранных регионах

        results.append({
            'word': w.word,
            'accent': w.accent,
            'meaning': w.meaning,
            'grammatical_features': w.grammatical_features,
            'subcategories': list(w.subcategories.values_list('name', flat=True)),
            'regions': list(region_names),
            'examples': examples
        })
    
    return JsonResponse({
        'results': results,
        'has_next': page_obj.has_next(),
        'has_prev': page_obj.has_previous(),
        'current_page': page_obj.number,
        'total_pages': paginator.num_pages
    })

@require_GET
def map_api(request):
    """Замена results_map.php"""
    search = request.GET.get('search', '').strip()
    qs = Word.objects.filter(word__icontains=search) if search else Word.objects.all()
    
    # Предзагружаем связи через промежуточную таблицу
    qs = qs.prefetch_related('textwords__text__region')
    
    results = []
    for w in qs[:50]:
        regions = set()
        # Проходим по связям Word -> TextWord -> Text -> Region
        for tw in w.textwords.all():
            if tw.text.region:
                regions.add(tw.text.region.name)
        
        for reg in regions:
            results.append({
                'word': w.word,
                'accent': w.accent,
                'meaning': w.meaning,
                'grammatical_features': w.grammatical_features,
                'region': reg
            })
    return JsonResponse(results, safe=False)

@require_GET
def get_regions_api(request):
    """Возвращает список всех регионов"""
    regions = Region.objects.values('name').order_by('name')
    return JsonResponse(list(regions), safe=False)

@require_GET
def get_categories_api(request):
    """Возвращает категории с подкатегориями (для группировки)"""
    categories = Category.objects.prefetch_related('subcategories').order_by('name')
    data = []
    for cat in categories:
        data.append({
            'category': cat.name,
            'subcategories': list(cat.subcategories.values('name').order_by('name'))
        })
    return JsonResponse(data, safe=False)

@require_GET
def get_pos_api(request):
    """Возвращает список всех частей речи"""
    pos_list = Word.objects.values_list('part_of_speech', flat=True).distinct().order_by('part_of_speech')
    # Фильтруем пустые значения
    pos_list = [pos for pos in pos_list if pos and pos.strip()]
    return JsonResponse(list(pos_list), safe=False)