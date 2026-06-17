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

    path('simulations/', views.simulation_list, name='simulation_list'),
    path('simulations/create/', views.simulation_create, name='simulation_create'),
    path('simulations/<int:pk>/', views.simulation_detail, name='simulation_detail'),
    path('simulations/<int:pk>/run/', views.simulation_run, name='simulation_run'),
    path('simulations/<int:pk>/delete/', views.simulation_delete, name='simulation_delete'),

    path('peak-hours/', views.peak_hour_list, name='peak_hour_list'),
    path('peak-hours/create/', views.peak_hour_create, name='peak_hour_create'),
    path('peak-hours/<int:pk>/update/', views.peak_hour_update, name='peak_hour_update'),
    path('peak-hours/<int:pk>/delete/', views.peak_hour_delete, name='peak_hour_delete'),

    path('blockade-events/', views.blockade_event_list, name='blockade_event_list'),
    path('blockade-events/create/', views.blockade_event_create, name='blockade_event_create'),
    path('blockade-events/<int:pk>/update/', views.blockade_event_update, name='blockade_event_update'),
    path('blockade-events/<int:pk>/delete/', views.blockade_event_delete, name='blockade_event_delete'),

    path('blockade-drills/', views.blockade_drill_list, name='blockade_drill_list'),
    path('blockade-drills/create/', views.blockade_drill_create, name='blockade_drill_create'),
    path('blockade-drills/<int:pk>/', views.blockade_drill_detail, name='blockade_drill_detail'),
    path('blockade-drills/<int:pk>/run/', views.blockade_drill_run, name='blockade_drill_run'),
    path('blockade-drills/<int:pk>/delete/', views.blockade_drill_delete, name='blockade_drill_delete'),

    path('api/stations/', views.api_stations, name='api_stations'),
    path('api/roads/', views.api_roads, name='api_roads'),
    path('api/roads/create/', views.api_create_road, name='api_create_road'),
    path('api/strategies/', views.api_strategies, name='api_strategies'),
    path('api/calculate/', views.api_calculate_route, name='api_calculate_route'),
    path('api/tasks/<int:pk>/plans/', views.api_task_plans, name='api_task_plans'),
    path('api/tasks/<int:task_pk>/segments/<int:segment_pk>/', views.api_segment_config, name='api_segment_config'),
    path('api/simulations/<int:pk>/result/', views.api_simulation_result, name='api_simulation_result'),
    path('api/blockade-drills/<int:pk>/result/', views.api_blockade_drill_result, name='api_blockade_drill_result'),
]
