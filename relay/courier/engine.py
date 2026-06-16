import math
from collections import defaultdict
from .models import Road, WeatherRecord, DeliveryTask, DeliverySegment


BASE_SPEED_LI_PER_SHICHEN = 60.0

GRADE_SPEED_FACTOR = {
    1: 1.0,
    2: 0.85,
    3: 0.65,
    4: 0.45,
    5: 0.25,
}

PRIORITY_SPEED_FACTOR = {
    1: 1.0,
    2: 1.4,
    3: 2.0,
}

HIGH_RISK_THRESHOLD = 2.5


def calculate_segment_time(road, weather_type=None, priority=1, strategy=None):
    speed = BASE_SPEED_LI_PER_SHICHEN

    grade_factor = GRADE_SPEED_FACTOR.get(road.grade, 0.85)
    speed *= grade_factor

    slope = road.slope or 0
    if slope > 0:
        slope_factor = max(0.2, 1.0 - slope * 0.03)
        speed *= slope_factor

    if weather_type:
        weather_factor = WeatherRecord.SEVERITY_MAP.get(weather_type, 1.0)
        speed /= weather_factor
    else:
        latest_weather = WeatherRecord.objects.filter(road=road).first()
        if latest_weather:
            speed /= latest_weather.speed_factor

    priority_factor = PRIORITY_SPEED_FACTOR.get(priority, 1.0)
    speed *= priority_factor

    if speed <= 0:
        speed = 0.1

    travel_time = road.distance / speed

    horse_change_time = 0.0
    if strategy and strategy.interval_distance and strategy.interval_distance > 0:
        num_changes = math.floor(road.distance / strategy.interval_distance)
        horse_change_time = num_changes * (strategy.change_time or 0)

    total_time = travel_time + horse_change_time

    is_high_risk = False
    if weather_type and WeatherRecord.SEVERITY_MAP.get(weather_type, 1.0) >= HIGH_RISK_THRESHOLD:
        is_high_risk = True
    elif not weather_type:
        latest_weather = WeatherRecord.objects.filter(road=road).first()
        if latest_weather and latest_weather.speed_factor >= HIGH_RISK_THRESHOLD:
            is_high_risk = True

    if road.grade >= 5:
        is_high_risk = True

    if slope > 20:
        is_high_risk = True

    return {
        'travel_time': round(travel_time, 2),
        'horse_change_time': round(horse_change_time, 2),
        'total_time': round(total_time, 2),
        'is_high_risk': is_high_risk,
        'speed': round(speed, 2),
        'distance': road.distance,
    }


def find_path(origin_id, destination_id):
    all_roads = Road.objects.select_related('from_station', 'to_station').all()
    graph = defaultdict(list)
    for road in all_roads:
        graph[road.from_station_id].append((road.to_station_id, road))

    visited = set()
    path_roads = []

    def dfs(current, target, roads):
        if current == target:
            return roads[:]
        if current in visited:
            return None
        visited.add(current)
        for next_id, road in graph[current]:
            result = dfs(next_id, target, roads + [road])
            if result is not None:
                return result
        visited.discard(current)
        return None

    return dfs(origin_id, destination_id, [])


def calculate_delivery_time(task, force_recalculate=False):
    if not force_recalculate and task.estimated_hours is not None and task.segments.exists():
        return task.estimated_hours

    path_roads = find_path(task.origin_id, task.destination_id)
    if not path_roads:
        task.has_high_risk = True
        task.estimated_hours = None
        task.save()
        return None

    strategy = task.strategy
    total_time = 0.0
    has_high_risk = False

    DeliverySegment.objects.filter(task=task).delete()

    for idx, road in enumerate(path_roads):
        result = calculate_segment_time(
            road=road,
            priority=task.priority,
            strategy=strategy,
        )

        DeliverySegment.objects.create(
            task=task,
            road=road,
            order=idx + 1,
            segment_time=result['total_time'],
            is_high_risk=result['is_high_risk'],
        )

        total_time += result['total_time']
        if result['is_high_risk']:
            has_high_risk = True

    task.estimated_hours = round(total_time, 2)
    task.has_high_risk = has_high_risk
    task.save()

    return task.estimated_hours


def recalculate_affected_tasks(road_id):
    affected_segments = DeliverySegment.objects.filter(road_id=road_id).select_related('task')
    task_ids = set(seg.task_id for seg in affected_segments)
    for task_id in task_ids:
        task = DeliveryTask.objects.get(pk=task_id)
        calculate_delivery_time(task, force_recalculate=True)


def get_analysis_data(task):
    segments = task.segments.select_related('road', 'road__from_station', 'road__to_station').all()
    if not segments:
        calculate_delivery_time(task, force_recalculate=True)
        segments = task.segments.select_related('road', 'road__from_station', 'road__to_station').all()

    chart_data = {
        'labels': [],
        'travel_times': [],
        'horse_change_times': [],
        'total_times': [],
        'risks': [],
        'distances': [],
        'speeds': [],
    }

    for seg in segments:
        road = seg.road
        result = calculate_segment_time(
            road=road,
            priority=task.priority,
            strategy=task.strategy,
        )
        chart_data['labels'].append(f'{road.from_station.code}→{road.to_station.code}')
        chart_data['travel_times'].append(result['travel_time'])
        chart_data['horse_change_times'].append(result['horse_change_time'])
        chart_data['total_times'].append(result['total_time'])
        chart_data['risks'].append(1 if result['is_high_risk'] else 0)
        chart_data['distances'].append(result['distance'])
        chart_data['speeds'].append(result['speed'])

    return chart_data
