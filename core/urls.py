# core/urls.py
from django.urls import path
from . import views
from django.views.generic import TemplateView

urlpatterns = [
    path('', TemplateView.as_view(template_name='index.html'), name='index'),
    path('dictionary/', TemplateView.as_view(template_name='dictionary.html'), name='dictionary'),
    path('map/', TemplateView.as_view(template_name='map.html'), name='map'),
    
    # API для JS
    path('api/search/', views.search_api, name='search_api'),
    path('api/map/', views.map_api, name='map_api'),

    # API для фильтров
    path('api/regions/', views.get_regions_api, name='get_regions'),
    path('api/categories/', views.get_categories_api, name='get_categories'),
    path('api/pos/', views.get_pos_api, name='get_pos'),
]