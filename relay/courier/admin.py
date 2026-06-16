from django.contrib import admin
from .models import Station, Road, HorseChangeStrategy, WeatherRecord, DeliveryTask, DeliverySegment


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'latitude', 'longitude']
    search_fields = ['code', 'name']


@admin.register(Road)
class RoadAdmin(admin.ModelAdmin):
    list_display = ['from_station', 'to_station', 'distance', 'slope', 'grade']
    list_filter = ['grade']


@admin.register(HorseChangeStrategy)
class HorseChangeStrategyAdmin(admin.ModelAdmin):
    list_display = ['name', 'interval_distance', 'change_time']


@admin.register(WeatherRecord)
class WeatherRecordAdmin(admin.ModelAdmin):
    list_display = ['road', 'weather_type', 'recorded_at']
    list_filter = ['weather_type']


@admin.register(DeliveryTask)
class DeliveryTaskAdmin(admin.ModelAdmin):
    list_display = ['task_code', 'origin', 'destination', 'priority', 'status', 'estimated_hours', 'has_high_risk']
    list_filter = ['status', 'priority', 'has_high_risk']


@admin.register(DeliverySegment)
class DeliverySegmentAdmin(admin.ModelAdmin):
    list_display = ['task', 'road', 'order', 'segment_time', 'is_high_risk']
