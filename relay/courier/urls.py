from django.urls import path
from . import views

app_name = 'courier'

urlpatterns = [
    path('', views.index, name='index'),

    path('stations/', views.station_list, name='station_list'),
    path('stations/create/', views.station_create, name='station_create'),
    path('stations/<int:pk>/update/', views.station_update, name='station_update'),
    path('stations/<int:pk>/delete/', views.station_delete, name='station_delete'),

    path('roads/', views.road_list, name='road_list'),
    path('roads/create/', views.road_create, name='road_create'),
    path('roads/<int:pk>/update/', views.road_update, name='road_update'),
    path('roads/<int:pk>/delete/', views.road_delete, name='road_delete'),

    path('strategies/', views.strategy_list, name='strategy_list'),
    path('strategies/create/', views.strategy_create, name='strategy_create'),
    path('strategies/<int:pk>/update/', views.strategy_update, name='strategy_update'),
    path('strategies/<int:pk>/delete/', views.strategy_delete, name='strategy_delete'),

    path('weather/', views.weather_list, name='weather_list'),
    path('weather/create/', views.weather_create, name='weather_create'),
    path('weather/<int:pk>/update/', views.weather_update, name='weather_update'),
    path('weather/<int:pk>/delete/', views.weather_delete, name='weather_delete'),

    path('tasks/', views.task_list, name='task_list'),
    path('tasks/create/', views.task_create, name='task_create'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/status/', views.task_update_status, name='task_update_status'),
    path('tasks/<int:pk>/recalculate/', views.task_recalculate, name='task_recalculate'),
    path('tasks/<int:pk>/delete/', views.task_delete, name='task_delete'),

    path('map/', views.map_view, name='map_view'),
    path('analysis/', views.analysis_dashboard, name='analysis_dashboard'),

    path('api/stations/', views.api_stations, name='api_stations'),
    path('api/roads/', views.api_roads, name='api_roads'),
    path('api/roads/create/', views.api_create_road, name='api_create_road'),
    path('api/strategies/', views.api_strategies, name='api_strategies'),
    path('api/calculate/', views.api_calculate_route, name='api_calculate_route'),
    path('api/tasks/<int:pk>/plans/', views.api_task_plans, name='api_task_plans'),
    path('api/tasks/<int:task_pk>/segments/<int:segment_pk>/', views.api_segment_config, name='api_segment_config'),
]
