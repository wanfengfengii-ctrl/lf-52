from django.contrib import admin
from .models import (
    Station, Road, HorseChangeStrategy, WeatherRecord,
    DeliveryTask, DeliverySegment, DeliveryPlan, PlanSegment,
    StationPeakHour, SimulationRun, SimTask, SimStationVisit,
    SimStationSnapshot, SimBottleneckStation,
    RoadBlockadeEvent, BlockadeDrill,
)


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'latitude', 'longitude', 'capacity', 'window_count', 'process_time', 'queue_rule']
    search_fields = ['code', 'name']
    list_filter = ['queue_rule']


@admin.register(StationPeakHour)
class StationPeakHourAdmin(admin.ModelAdmin):
    list_display = ['station', 'start_hour', 'end_hour', 'capacity_multiplier', 'process_delay_pct', 'label']
    list_filter = ['station']
    search_fields = ['station__code', 'station__name', 'label']


@admin.register(SimulationRun)
class SimulationRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'task_count', 'status', 'avg_wait_time', 'max_wait_time', 'total_delay_count', 'created_at']
    list_filter = ['status', 'enable_peak_hours']
    search_fields = ['name']


@admin.register(SimTask)
class SimTaskAdmin(admin.ModelAdmin):
    list_display = ['simulation', 'sim_task_code', 'priority', 'departure_time', 'arrival_time', 'total_wait_time', 'is_delayed']
    list_filter = ['priority', 'is_delayed']
    search_fields = ['sim_task_code']


@admin.register(SimStationVisit)
class SimStationVisitAdmin(admin.ModelAdmin):
    list_display = ['sim_task', 'station_code', 'visit_order', 'arrive_time', 'wait_duration', 'process_duration', 'in_peak_hour']
    list_filter = ['in_peak_hour', 'station_code']


@admin.register(SimStationSnapshot)
class SimStationSnapshotAdmin(admin.ModelAdmin):
    list_display = ['simulation', 'station_code', 'snapshot_time', 'queue_length', 'busy_windows', 'total_windows', 'utilization']
    list_filter = ['station_code', 'in_peak_hour']


@admin.register(SimBottleneckStation)
class SimBottleneckStationAdmin(admin.ModelAdmin):
    list_display = ['simulation', 'rank', 'station_code', 'station_name', 'total_visits', 'avg_wait_time', 'max_queue_length', 'bottleneck_score']
    list_filter = ['simulation']


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


@admin.register(RoadBlockadeEvent)
class RoadBlockadeEventAdmin(admin.ModelAdmin):
    list_display = ['name', 'event_type', 'road', 'station', 'start_hour', 'end_hour', 'severity', 'flow_rate']
    list_filter = ['event_type']
    search_fields = ['name']


@admin.register(BlockadeDrill)
class BlockadeDrillAdmin(admin.ModelAdmin):
    list_display = ['name', 'base_simulation', 'status', 'affected_task_count', 'reroute_cost_total', 'created_at']
    list_filter = ['status']
    search_fields = ['name']
