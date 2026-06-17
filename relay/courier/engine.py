import math
import heapq
from collections import defaultdict
from .models import Road, WeatherRecord, DeliveryTask, DeliverySegment, DeliveryPlan, PlanSegment, Station


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
RISK_PENALTY_FACTOR = 2.0
DELAY_RISK_THRESHOLD = 0.3


def calculate_segment_time(road, weather_type=None, priority=1, strategy=None, segment=None):
    speed = BASE_SPEED_LI_PER_SHICHEN

    grade_factor = GRADE_SPEED_FACTOR.get(road.grade, 0.85)
    speed *= grade_factor

    slope = road.slope or 0
    if slope > 0:
        slope_factor = max(0.2, 1.0 - slope * 0.03)
        speed *= slope_factor

    effective_weather = weather_type
    if segment and segment.override_weather:
        effective_weather = segment.override_weather

    if effective_weather:
        weather_factor = WeatherRecord.SEVERITY_MAP.get(effective_weather, 1.0)
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

    effective_strategy = strategy
    if segment and segment.override_strategy:
        effective_strategy = segment.override_strategy

    horse_change_time = 0.0
    if effective_strategy and effective_strategy.interval_distance and effective_strategy.interval_distance > 0:
        num_changes = math.floor(road.distance / effective_strategy.interval_distance)
        horse_change_time = num_changes * (effective_strategy.change_time or 0)

    process_time = 0.0
    if road.to_station:
        process_time = road.to_station.process_time or 0.0

    total_time = travel_time + horse_change_time + process_time

    is_high_risk = False
    risk_score = 0.0

    if effective_weather:
        wf = WeatherRecord.SEVERITY_MAP.get(effective_weather, 1.0)
        if wf >= HIGH_RISK_THRESHOLD:
            is_high_risk = True
            risk_score += 1.0
    else:
        latest_weather = WeatherRecord.objects.filter(road=road).first()
        if latest_weather and latest_weather.speed_factor >= HIGH_RISK_THRESHOLD:
            is_high_risk = True
            risk_score += 1.0

    if road.grade >= 5:
        is_high_risk = True
        risk_score += 0.8

    if slope > 20:
        is_high_risk = True
        risk_score += 0.6
    elif slope > 10:
        risk_score += 0.3

    return {
        'travel_time': round(travel_time, 2),
        'horse_change_time': round(horse_change_time, 2),
        'process_time': round(process_time, 2),
        'total_time': round(total_time, 2),
        'is_high_risk': is_high_risk,
        'risk_score': round(risk_score, 2),
        'speed': round(speed, 2),
        'distance': road.distance,
        'grade': road.grade,
        'slope': slope,
    }


def _build_graph():
    all_roads = Road.objects.select_related('from_station', 'to_station').all()
    graph = defaultdict(list)
    for road in all_roads:
        graph[road.from_station_id].append((road.to_station_id, road))
    return graph


def _dijkstra(graph, origin_id, destination_id, priority=1, strategy=None, optimize='time'):
    dist = {origin_id: 0.0}
    risk = {origin_id: 0.0}
    prev = {}
    pq = [(0.0, 0.0, origin_id)]
    visited = set()

    while pq:
        current_cost, current_risk, current = heapq.heappop(pq)
        if current in visited:
            continue
        visited.add(current)
        if current == destination_id:
            break

        for next_id, road in graph.get(current, []):
            seg_result = calculate_segment_time(road, priority=priority, strategy=strategy)

            if optimize == 'time':
                edge_cost = seg_result['total_time']
            elif optimize == 'safe':
                edge_cost = seg_result['risk_score'] * 10 + seg_result['total_time'] * 0.1
            elif optimize == 'balanced':
                edge_cost = seg_result['total_time'] + seg_result['risk_score'] * RISK_PENALTY_FACTOR
            else:
                edge_cost = seg_result['total_time']

            new_cost = dist[current] + edge_cost
            new_risk = risk.get(current, 0.0) + seg_result['risk_score']

            if next_id not in dist or new_cost < dist[next_id]:
                dist[next_id] = new_cost
                risk[next_id] = new_risk
                prev[next_id] = (current, road, seg_result)
                heapq.heappush(pq, (new_cost, new_risk, next_id))

    if destination_id not in prev and destination_id != origin_id:
        return None

    path_roads = []
    path_results = []
    current = destination_id
    while current != origin_id and current in prev:
        prev_station, road, seg_result = prev[current]
        path_roads.append(road)
        path_results.append(seg_result)
        current = prev_station

    path_roads.reverse()
    path_results.reverse()
    return path_roads, path_results


def find_path(origin_id, destination_id, optimize='time', priority=1, strategy=None):
    graph = _build_graph()
    result = _dijkstra(graph, origin_id, destination_id, priority=priority, strategy=strategy, optimize=optimize)
    if result is None:
        return None
    return result[0]


def find_all_paths(origin_id, destination_id, priority=1, strategy=None, max_paths=5):
    graph = _build_graph()
    results = []

    strategies = [
        ('fastest', 'time'),
        ('safest', 'safe'),
        ('balanced', 'balanced'),
    ]

    for plan_type, optimize in strategies:
        result = _dijkstra(graph, origin_id, destination_id, priority=priority, strategy=strategy, optimize=optimize)
        if result:
            results.append((plan_type, result[0], result[1]))

    if len(results) < max_paths:
        result = _dijkstra(graph, origin_id, destination_id, priority=priority, strategy=strategy, optimize='time')
        if result:
            base_roads = result[0]
            if base_roads and len(base_roads) >= 3:
                try:
                    alt_graph = _build_graph()
                    mid_idx = len(base_roads) // 2
                    skip_road_id = base_roads[mid_idx].pk
                    filtered_graph = defaultdict(list)
                    for from_id, edges in alt_graph.items():
                        for to_id, road in edges:
                            if road.pk != skip_road_id:
                                filtered_graph[from_id].append((to_id, road))
                    alt_result = _dijkstra(filtered_graph, origin_id, destination_id, priority=priority, strategy=strategy, optimize='time')
                    if alt_result:
                        alt_roads = alt_result[0]
                        existing_road_ids = set(r.pk for _, roads, _ in results for r in roads)
                        if any(r.pk not in existing_road_ids for r in alt_roads):
                            results.append(('alternative', alt_roads, alt_result[1]))
                except Exception:
                    pass

    return results


def _compute_delay_probability(total_time, deadline_hours, risk_count, station_count):
    if deadline_hours is None or deadline_hours <= 0:
        return 0.0
    ratio = total_time / deadline_hours
    base_prob = max(0.0, (ratio - 0.7) / 0.5)
    risk_factor = min(1.0, risk_count * 0.15 + station_count * 0.02)
    prob = min(1.0, base_prob * 0.6 + risk_factor * 0.4)
    return round(prob, 2)


def generate_all_plans(task, force_recalculate=False):
    if not force_recalculate and task.plans.exists():
        return list(task.plans.select_related().all())

    task.plans.all().delete()

    path_results = find_all_paths(
        task.origin_id, task.destination_id,
        priority=task.priority, strategy=task.strategy
    )

    plans = []
    for plan_type, path_roads, path_results_data in path_results:
        if not path_roads:
            continue

        total_time = 0.0
        total_distance = 0.0
        risk_count = 0
        current_time = task.departure_offset or 0.0

        plan = DeliveryPlan.objects.create(
            task=task,
            plan_type=plan_type,
            total_time=0,
        )

        for idx, (road, seg_result) in enumerate(zip(path_roads, path_results_data)):
            departure = current_time
            arrival = current_time + seg_result['total_time']

            strategy_name = task.strategy.name if task.strategy else '默认策略'
            weather_display = '晴朗'
            latest_weather = WeatherRecord.objects.filter(road=road).first()
            if latest_weather:
                weather_display = latest_weather.get_weather_type_display()

            PlanSegment.objects.create(
                plan=plan,
                road=road,
                order=idx + 1,
                segment_time=seg_result['total_time'],
                travel_time=seg_result['travel_time'],
                horse_change_time=seg_result['horse_change_time'],
                process_time=seg_result['process_time'],
                is_high_risk=seg_result['is_high_risk'],
                departure_time=round(departure, 2),
                arrival_time=round(arrival, 2),
                strategy_name=strategy_name,
                weather_display=weather_display,
            )

            total_time += seg_result['total_time']
            total_distance += seg_result['distance']
            if seg_result['is_high_risk']:
                risk_count += 1
            current_time = arrival

        station_count = len(path_roads)
        delay_prob = _compute_delay_probability(
            total_time, task.deadline_hours, risk_count, station_count
        )
        plan.total_time = round(total_time, 2)
        plan.total_distance = round(total_distance, 2)
        plan.risk_count = risk_count
        plan.station_count = station_count
        plan.is_delay_risk = delay_prob >= DELAY_RISK_THRESHOLD
        plan.delay_probability = delay_prob
        plan.save()
        plans.append(plan)

    return plans


def calculate_delivery_time(task, force_recalculate=False):
    plans = generate_all_plans(task, force_recalculate=force_recalculate)
    if not plans:
        task.has_high_risk = True
        task.estimated_hours = None
        task.delay_warning = False
        task.save()
        return None

    selected_type = task.selected_plan_type or 'fastest'
    selected_plan = None
    for p in plans:
        if p.plan_type == selected_type:
            selected_plan = p
            break
    if selected_plan is None:
        selected_plan = plans[0]

    DeliverySegment.objects.filter(task=task).delete()
    for plan_seg in selected_plan.segments.all().order_by('order'):
        seg = DeliverySegment.objects.create(
            task=task,
            road=plan_seg.road,
            order=plan_seg.order,
            segment_time=plan_seg.segment_time,
            travel_time=plan_seg.travel_time,
            horse_change_time=plan_seg.horse_change_time,
            process_time=plan_seg.process_time,
            is_high_risk=plan_seg.is_high_risk,
            departure_time=plan_seg.departure_time,
            arrival_time=plan_seg.arrival_time,
        )
        if seg.order == 1:
            seg.departure_time = task.departure_offset
            seg.save()

    task.estimated_hours = selected_plan.total_time
    task.has_high_risk = selected_plan.risk_count > 0
    task.delay_warning = selected_plan.is_delay_risk
    task.save()
    return task.estimated_hours


def recalculate_affected_tasks(road_id):
    affected_segments = DeliverySegment.objects.filter(road_id=road_id).select_related('task')
    affected_plan_segments = PlanSegment.objects.filter(road_id=road_id).select_related('plan__task')
    task_ids = set(seg.task_id for seg in affected_segments)
    for ps in affected_plan_segments:
        task_ids.add(ps.plan.task_id)
    for task_id in task_ids:
        try:
            task = DeliveryTask.objects.get(pk=task_id)
            calculate_delivery_time(task, force_recalculate=True)
        except DeliveryTask.DoesNotExist:
            pass


def get_analysis_data(task):
    segments = task.segments.select_related('road', 'road__from_station', 'road__to_station').all()
    if not segments:
        calculate_delivery_time(task, force_recalculate=True)
        segments = task.segments.select_related('road', 'road__from_station', 'road__to_station').all()

    chart_data = {
        'labels': [],
        'travel_times': [],
        'horse_change_times': [],
        'process_times': [],
        'total_times': [],
        'risks': [],
        'distances': [],
        'speeds': [],
        'departures': [],
        'arrivals': [],
    }

    for seg in segments:
        road = seg.road
        result = calculate_segment_time(
            road=road,
            priority=task.priority,
            strategy=task.strategy,
            segment=seg,
        )
        chart_data['labels'].append(f'{road.from_station.code}→{road.to_station.code}')
        chart_data['travel_times'].append(result['travel_time'])
        chart_data['horse_change_times'].append(result['horse_change_time'])
        chart_data['process_times'].append(result['process_time'])
        chart_data['total_times'].append(result['total_time'])
        chart_data['risks'].append(1 if result['is_high_risk'] else 0)
        chart_data['distances'].append(result['distance'])
        chart_data['speeds'].append(result['speed'])
        chart_data['departures'].append(seg.departure_time or 0)
        chart_data['arrivals'].append(seg.arrival_time or 0)

    return chart_data


def get_plan_comparison_data(task):
    plans = task.plans.select_related().all()
    if not plans:
        generate_all_plans(task, force_recalculate=True)
        plans = task.plans.select_related().all()

    comparison = []
    for plan in plans:
        plan_segments = plan.segments.select_related('road', 'road__from_station', 'road__to_station').all().order_by('order')
        seg_data = []
        for ps in plan_segments:
            seg_data.append({
                'order': ps.order,
                'from': ps.road.from_station.code,
                'to': ps.road.to_station.code,
                'distance': ps.road.distance,
                'segment_time': ps.segment_time,
                'travel_time': ps.travel_time,
                'horse_change_time': ps.horse_change_time,
                'process_time': ps.process_time,
                'is_high_risk': ps.is_high_risk,
                'departure_time': ps.departure_time,
                'arrival_time': ps.arrival_time,
                'strategy_name': ps.strategy_name,
                'weather_display': ps.weather_display,
            })
        comparison.append({
            'plan_type': plan.plan_type,
            'plan_type_display': plan.get_plan_type_display(),
            'total_time': plan.total_time,
            'total_distance': plan.total_distance,
            'risk_count': plan.risk_count,
            'station_count': plan.station_count,
            'is_delay_risk': plan.is_delay_risk,
            'delay_probability': plan.delay_probability,
            'segments': seg_data,
        })
    return comparison


def get_gantt_data(task):
    plans = task.plans.select_related().all()
    if not plans:
        generate_all_plans(task, force_recalculate=True)
        plans = task.plans.select_related().all()

    gantt = []
    for plan in plans:
        plan_segs = plan.segments.select_related('road', 'road__from_station', 'road__to_station').order_by('order')
        for ps in plan_segs:
            gantt.append({
                'plan_type': plan.plan_type,
                'plan_type_display': plan.get_plan_type_display(),
                'task': f'{ps.road.from_station.code}→{ps.road.to_station.code}',
                'start': ps.departure_time or 0,
                'end': ps.arrival_time or 0,
                'is_high_risk': ps.is_high_risk,
                'segment_time': ps.segment_time,
            })
    return gantt
