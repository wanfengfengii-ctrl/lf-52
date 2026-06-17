from django.contrib import admin
from .models import (
    Station, Road, HorseChangeStrategy, WeatherRecord,
    DeliveryTask, DeliverySegment, DeliveryPlan, PlanSegment
)


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'latitude', 'longitude', 'capacity', 'process_time']
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
    list_display = ['task_code', 'origin', 'destination', 'priority', 'status', 'estimated_hours', 'has_high_risk', 'delay_warning']
    list_filter = ['status', 'priority', 'has_high_risk', 'delay_warning', 'selected_plan_type']


@admin.register(DeliverySegment)
class DeliverySegmentAdmin(admin.ModelAdmin):
    list_display = ['task', 'road', 'order', 'segment_time', 'is_high_risk', 'departure_time', 'arrival_time']
    list_filter = ['is_high_risk']


@admin.register(DeliveryPlan)
class DeliveryPlanAdmin(admin.ModelAdmin):
    list_display = ['task', 'plan_type', 'total_time', 'total_distance', 'risk_count', 'is_delay_risk', 'delay_probability']
    list_filter = ['plan_type', 'is_delay_risk']


@admin.register(PlanSegment)
class PlanSegmentAdmin(admin.ModelAdmin):
    list_display = ['plan', 'order', 'road', 'segment_time', 'is_high_risk', 'departure_time', 'arrival_time']
    list_filter = ['is_high_risk']
