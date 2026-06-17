import math
import random
import heapq
from collections import defaultdict
from .models import (
    Station, StationPeakHour, SimulationRun, SimTask,
    SimStationVisit, SimStationSnapshot, SimBottleneckStation,
    Road, RoadBlockadeEvent, BlockadeDrill,
)
from .engine import _build_graph, _dijkstra, calculate_segment_time
from .simulation_engine import (
    QueueSimulationEngine, StationQueue, run_simulation, get_simulation_result_data,
    EVENT_TASK_ARRIVE_AT_STATION, EVENT_STATION_PROCESS_DONE,
    EVENT_SNAPSHOT, EVENT_TASK_FINISH,
)


class BlockadeSimulationEngine(QueueSimulationEngine):
    def __init__(self, simulation_run, blockade_events=None):
        super().__init__(simulation_run)
        self.blockade_events = blockade_events or []
        self.blocked_road_ids = set()
        self.restricted_roads = {}
        self.down_station_ids = set()
        self.military_priorities = {}
        self._apply_blockade_events()

    def _apply_blockade_events(self):
        for event in self.blockade_events:
            if event.event_type == 'road_blocked' and event.road_id:
                self.blocked_road_ids.add(event.road_id)
            elif event.event_type == 'road_restricted' and event.road_id:
                self.restricted_roads[event.road_id] = {
                    'flow_rate': event.flow_rate,
                    'severity': event.severity,
                    'start_hour': event.start_hour,
                    'end_hour': event.end_hour,
                    'reroute_cost_multiplier': event.reroute_cost_multiplier,
                }
            elif event.event_type == 'station_down' and event.station_id:
                self.down_station_ids.add(event.station_id)
            elif event.event_type == 'military_priority':
                target = event.station_id or event.road_id
                if target:
                    self.military_priorities[target] = {
                        'priority_level': event.military_priority_level,
                        'start_hour': event.start_hour,
                        'end_hour': event.end_hour,
                    }

    def _is_road_blocked(self, road_id):
        return road_id in self.blocked_road_ids

    def _is_road_restricted(self, road_id, current_time):
        info = self.restricted_roads.get(road_id)
        if not info:
            return False
        t = current_time % 24.0
        return info['start_hour'] <= t < info['end_hour']

    def _is_station_down(self, station_id, current_time):
        if station_id not in self.down_station_ids:
            return False
        for event in self.blockade_events:
            if event.event_type == 'station_down' and event.station_id == station_id:
                t = current_time % 24.0
                if event.start_hour <= t < event.end_hour:
                    return True
        return False

    def _is_military_priority_active(self, target_id, current_time):
        info = self.military_priorities.get(target_id)
        if not info:
            return False
        t = current_time % 24.0
        return info['start_hour'] <= t < info['end_hour']

    def _generate_task_routes(self):
        stations = list(Station.objects.all())
        if len(stations) < 2:
            return []

        graph = _build_graph()
        filtered_graph = defaultdict(list)
        for from_id, edges in graph.items():
            for to_id, road in edges:
                if road.pk not in self.blocked_road_ids:
                    filtered_graph[from_id].append((to_id, road))

        routes = []
        attempts = 0
        while len(routes) < self.task_count and attempts < self.task_count * 10:
            attempts += 1
            origin = random.choice(stations)
            dest = random.choice(stations)
            if origin.pk == dest.pk:
                continue
            if origin.pk in self.down_station_ids or dest.pk in self.down_station_ids:
                continue
            result = _dijkstra(
                filtered_graph, origin.pk, dest.pk,
                priority=1, strategy=None, optimize='time'
            )
            if not result:
                result = _dijkstra(
                    graph, origin.pk, dest.pk,
                    priority=1, strategy=None, optimize='time'
                )
            if not result:
                continue
            path_roads, path_results = result
            if not path_roads:
                continue

            r = random.random()
            cum = 0.0
            priority = 1
            for p_str, prob in sorted(self.priority_distribution.items()):
                cum += float(prob)
                if r <= cum:
                    priority = int(p_str)
                    break

            routes.append({
                'origin_id': origin.pk,
                'destination_id': dest.pk,
                'priority': priority,
                'path_roads': path_roads,
                'path_results': path_results,
            })
        return routes

    def _calc_travel_time_between(self, from_station_id, to_station_id, road, priority):
        current_time = 0
        if self._is_road_blocked(road.pk):
            return road.distance / (60.0 * 0.1)

        seg_result = calculate_segment_time(road, priority=priority)
        travel_time = seg_result['travel_time']

        if self._is_road_restricted(road.pk, current_time):
            info = self.restricted_roads[road.pk]
            flow_rate = max(0.05, info['flow_rate'])
            travel_time = travel_time / flow_rate

        if self._is_military_priority_active(road.pk, current_time) and priority < 3:
            travel_time *= 1.5

        return travel_time

    def run(self):
        routes = self._generate_task_routes()
        if not routes:
            return {'success': False, 'error': '无法在封锁条件下生成任务路线'}

        routes = self._generate_departure_times(routes)

        sim_task_objs = []
        for idx, route in enumerate(routes):
            sim_code = f'BDRILL-{self.sim_run.pk:04d}-{idx + 1:04d}'
            sim_task_obj = {
                'sim_task_code': sim_code,
                'origin_id': route['origin_id'],
                'destination_id': route['destination_id'],
                'priority': route['priority'],
                'departure_time': route['departure_time'],
                'path_roads': route['path_roads'],
                'path_results': route['path_results'],
                'current_station_idx': 0,
                'expected_total_no_congestion': 0.0,
                'visits': [],
            }
            sim_task_objs.append(sim_task_obj)

        snapshot_interval = max(0.1, (self.sim_end - self.sim_start) / 50.0)
        for t_int in range(int(math.ceil((self.sim_end - self.sim_start) / snapshot_interval))):
            snap_time = self.sim_start + t_int * snapshot_interval
            self._schedule_event(snap_time, EVENT_SNAPSHOT, {})

        for sim_task_obj in sim_task_objs:
            self._schedule_event(
                sim_task_obj['departure_time'],
                EVENT_TASK_ARRIVE_AT_STATION,
                {'sim_task_obj': sim_task_obj, 'station_idx': 0}
            )

        current_time = self.sim_start

        while self.event_queue:
            event_time, _, event_type, data = heapq.heappop(self.event_queue)
            current_time = event_time

            if event_type == EVENT_SNAPSHOT:
                for sid, sq in self.station_queues.items():
                    sq.record_queue_length(current_time)
                    sq.record_utilization(current_time)
                    ph = sq.is_peak_hour_config(current_time)
                    self.snapshots.append({
                        'station_id': sid,
                        'station_code': self.station_id_to_code[sid],
                        'snapshot_time': round(current_time, 3),
                        'queue_length': len(sq.queue),
                        'busy_windows': sq.busy_windows,
                        'total_windows': sq.effective_windows(current_time),
                        'utilization': round(sq.busy_windows / max(1, sq.effective_windows(current_time)) * 100, 1),
                        'in_peak_hour': ph is not None,
                        'station_down': self._is_station_down(sid, current_time),
                        'military_priority': self._is_military_priority_active(sid, current_time),
                    })
                continue

            if event_type == EVENT_TASK_ARRIVE_AT_STATION:
                sim_task_obj = data['sim_task_obj']
                station_idx = data['station_idx']
                path_roads = sim_task_obj['path_roads']
                is_depart_from_origin = station_idx == 0

                if is_depart_from_origin:
                    road = path_roads[0]
                    to_station_id = road.from_station_id
                    sim_task_obj['current_time'] = current_time
                else:
                    road = path_roads[station_idx - 1]
                    to_station_id = road.to_station_id

                if self._is_station_down(to_station_id, current_time):
                    path_roads_remaining = path_roads[station_idx:]
                    found_alternative = False
                    for alt_idx, alt_road in enumerate(path_roads_remaining):
                        if not self._is_station_down(alt_road.to_station_id, current_time):
                            to_station_id = alt_road.to_station_id
                            station_idx = station_idx + alt_idx + 1
                            found_alternative = True
                            break
                    if not found_alternative:
                        sim_task_obj['arrival_time'] = round(current_time, 3)
                        sim_task_obj['blocked'] = True
                        continue

                sq = self.station_queues[to_station_id]
                self.global_arrival_counter += 1
                arrival_order = self.global_arrival_counter

                effective_priority = sim_task_obj['priority']
                if self._is_military_priority_active(to_station_id, current_time):
                    effective_priority = max(effective_priority, 3)

                visit_record = {
                    'station_id': to_station_id,
                    'station_code': sq.station_code,
                    'visit_order': station_idx + (0 if is_depart_from_origin else 1),
                    'arrive_time': round(current_time, 3),
                    'in_peak_hour': sq.is_peak_hour_config(current_time) is not None,
                    'queue_position_on_arrival': len(sq.queue),
                }

                eff_process = sq.effective_process_time(current_time, effective_priority)
                if self._is_station_down(to_station_id, current_time):
                    eff_process *= 5.0

                travel_next = 0.0
                if station_idx < len(path_roads):
                    next_road = path_roads[station_idx]
                    if is_depart_from_origin:
                        travel_next = self._calc_travel_time_between(
                            next_road.from_station_id,
                            next_road.to_station_id,
                            next_road,
                            effective_priority
                        )
                        sim_task_obj['expected_total_no_congestion'] += travel_next + eff_process

                queue_pos = sq.add_to_queue(
                    effective_priority, arrival_order, sim_task_obj, visit_record)
                visit_record['queue_enter_time'] = round(current_time, 3)

                started_items = sq.try_start_processing(current_time)
                for s_item in started_items:
                    s_priority, s_order, s_wkey, s_task_obj, s_visit = s_item
                    s_process_time = sq.effective_process_time(current_time, s_priority)
                    s_visit['process_start_time'] = round(current_time, 3)
                    s_visit['wait_duration'] = round(current_time - s_visit['queue_enter_time'], 3)
                    sq.total_wait_times.append(s_visit['wait_duration'])
                    finish_time = current_time + s_process_time
                    s_visit['process_duration'] = round(s_process_time, 3)
                    self._schedule_event(
                        finish_time, EVENT_STATION_PROCESS_DONE,
                        {
                            'sim_task_obj': s_task_obj,
                            'station_id': to_station_id,
                            'visit_record': s_visit,
                        }
                    )
                continue

            if event_type == EVENT_STATION_PROCESS_DONE:
                sim_task_obj = data['sim_task_obj']
                station_id = data['station_id']
                visit_record = data['visit_record']

                sq = self.station_queues[station_id]
                sq.finish_processing()
                visit_record['process_end_time'] = round(current_time, 3)
                visit_record['depart_time'] = round(current_time, 3)

                sim_task_obj['visits'].append(visit_record)
                sim_task_obj['current_station_idx'] = sim_task_obj.get('current_station_idx', 0) + 1

                path_roads = sim_task_obj['path_roads']
                next_idx = sim_task_obj['current_station_idx']

                if next_idx >= len(path_roads):
                    final_road = path_roads[-1]
                    final_dest_id = final_road.to_station_id
                    if station_id == final_dest_id:
                        self._schedule_event(
                            current_time, EVENT_TASK_FINISH,
                            {'sim_task_obj': sim_task_obj}
                        )
                        continue

                if next_idx < len(path_roads):
                    next_road = path_roads[next_idx]
                    travel_time = self._calc_travel_time_between(
                        next_road.from_station_id,
                        next_road.to_station_id,
                        next_road,
                        sim_task_obj['priority']
                    )
                    arrive_time = current_time + travel_time
                    self._schedule_event(
                        arrive_time, EVENT_TASK_ARRIVE_AT_STATION,
                        {'sim_task_obj': sim_task_obj, 'station_idx': next_idx + 1}
                    )
                else:
                    self._schedule_event(
                        current_time, EVENT_TASK_FINISH,
                        {'sim_task_obj': sim_task_obj}
                    )

                next_started = sq.try_start_processing(current_time)
                for ns_item in next_started:
                    ns_priority, ns_order, ns_wkey, ns_task_obj, ns_visit = ns_item
                    ns_process_time = sq.effective_process_time(current_time, ns_priority)
                    ns_visit['process_start_time'] = round(current_time, 3)
                    ns_visit['wait_duration'] = round(current_time - ns_visit['queue_enter_time'], 3)
                    sq.total_wait_times.append(ns_visit['wait_duration'])
                    ns_finish = current_time + ns_process_time
                    ns_visit['process_duration'] = round(ns_process_time, 3)
                    self._schedule_event(
                        ns_finish, EVENT_STATION_PROCESS_DONE,
                        {
                            'sim_task_obj': ns_task_obj,
                            'station_id': station_id,
                            'visit_record': ns_visit,
                        }
                    )
                continue

            if event_type == EVENT_TASK_FINISH:
                sim_task_obj = data['sim_task_obj']
                sim_task_obj['arrival_time'] = round(current_time, 3)
                continue

        completed_tasks = [t for t in sim_task_objs if 'arrival_time' in t]
        self._save_results(completed_tasks)

        return {
            'success': True,
            'total_tasks': len(sim_task_objs),
            'completed_tasks': len(completed_tasks),
        }


def run_blockade_drill(drill_id):
    from django.utils import timezone

    drill = BlockadeDrill.objects.get(pk=drill_id)
    base_sim = drill.base_simulation

    if base_sim.status != 'completed':
        return {'success': False, 'error': '基准仿真尚未完成，请先运行基准仿真'}

    drill.status = 'running'
    drill.save()

    try:
        before_result = get_simulation_result_data(base_sim.pk)
        drill.before_avg_wait = base_sim.avg_wait_time
        drill.before_max_wait = base_sim.max_wait_time
        drill.before_avg_total = base_sim.avg_total_time
        drill.before_delay_count = base_sim.total_delay_count
        drill.before_bottleneck_codes = [
            bn['code'] for bn in before_result['bottleneck_list'][:5]
        ]

        blockade_events = list(drill.blockade_events.all())

        drill_sim = SimulationRun.objects.create(
            name=f'[封锁推演] {drill.name}',
            description=f'封锁推演副本 - 基于仿真 #{base_sim.pk}',
            sim_start_time=base_sim.sim_start_time,
            sim_end_time=base_sim.sim_end_time,
            random_seed=base_sim.random_seed,
            task_count=base_sim.task_count,
            enable_peak_hours=base_sim.enable_peak_hours,
            priority_distribution=base_sim.priority_distribution or {'1': 0.6, '2': 0.3, '3': 0.1},
            status='running',
        )

        engine = BlockadeSimulationEngine(drill_sim, blockade_events=blockade_events)
        result = engine.run()

        if not result['success']:
            drill_sim.status = 'failed'
            drill_sim.error_message = result.get('error', '未知错误')
            drill_sim.save()
            drill.status = 'failed'
            drill.error_message = result.get('error', '未知错误')
            drill.finished_at = timezone.now()
            drill.save()
            return result

        after_result = get_simulation_result_data(drill_sim.pk)
        drill.after_avg_wait = drill_sim.avg_wait_time
        drill.after_max_wait = drill_sim.max_wait_time
        drill.after_avg_total = drill_sim.avg_total_time
        drill.after_delay_count = drill_sim.total_delay_count
        drill.after_bottleneck_codes = [
            bn['code'] for bn in after_result['bottleneck_list'][:5]
        ]

        affected_count = 0
        reroute_cost = 0.0
        for event in blockade_events:
            if event.event_type in ('road_blocked', 'road_restricted') and event.road_id:
                road = Road.objects.get(pk=event.road_id)
                seg_count = SimStationVisit.objects.filter(
                    sim_task__simulation=drill_sim,
                    station_code=road.from_station.code
                ).count()
                affected_count += seg_count
                reroute_cost += event.reroute_cost_multiplier * seg_count * (1 + event.severity * 0.1)
            elif event.event_type == 'station_down' and event.station_id:
                station = Station.objects.get(pk=event.station_id)
                visit_count = SimStationVisit.objects.filter(
                    sim_task__simulation=drill_sim,
                    station_code=station.code
                ).count()
                affected_count += visit_count
                reroute_cost += visit_count * event.severity * 0.5

        drill.affected_task_count = affected_count
        drill.reroute_cost_total = round(reroute_cost, 2)

        congestion_transfer = _compute_congestion_transfer(base_sim, drill_sim)
        drill.congestion_transfer = congestion_transfer

        impact_timeline = _build_impact_timeline(blockade_events, drill_sim)
        drill.impact_timeline = impact_timeline

        bottleneck_diff = _compute_bottleneck_diff(before_result, after_result)
        drill.bottleneck_diff = bottleneck_diff

        recovery_strategies = _generate_recovery_strategies(
            blockade_events, before_result, after_result, drill
        )
        drill.recovery_strategies = recovery_strategies

        drill.status = 'completed'
        drill.finished_at = timezone.now()
        drill.save()

        return {'success': True, 'drill_id': drill.pk}

    except Exception as e:
        drill.status = 'failed'
        drill.error_message = str(e)
        drill.finished_at = timezone.now()
        drill.save()
        return {'success': False, 'error': str(e)}


def _compute_congestion_transfer(base_sim, drill_sim):
    base_bottlenecks = {
        bn.station_code: bn for bn in base_sim.bottleneck_stations.all()
    }
    drill_bottlenecks = {
        bn.station_code: bn for bn in drill_sim.bottleneck_stations.all()
    }

    transfer = {}
    all_codes = set(base_bottlenecks.keys()) | set(drill_bottlenecks.keys())

    for code in all_codes:
        base_bn = base_bottlenecks.get(code)
        drill_bn = drill_bottlenecks.get(code)
        base_wait = base_bn.avg_wait_time if base_bn else 0
        drill_wait = drill_bn.avg_wait_time if drill_bn else 0
        base_queue = base_bn.avg_queue_length if base_bn else 0
        drill_queue = drill_bn.avg_queue_length if drill_bn else 0
        base_score = base_bn.bottleneck_score if base_bn else 0
        drill_score = drill_bn.bottleneck_score if drill_bn else 0

        transfer[code] = {
            'base_avg_wait': round(base_wait, 4),
            'drill_avg_wait': round(drill_wait, 4),
            'wait_diff': round(drill_wait - base_wait, 4),
            'base_avg_queue': round(base_queue, 4),
            'drill_avg_queue': round(drill_queue, 4),
            'queue_diff': round(drill_queue - base_queue, 4),
            'base_score': round(base_score, 2),
            'drill_score': round(drill_score, 2),
            'score_diff': round(drill_score - base_score, 2),
        }

    return transfer


def _build_impact_timeline(blockade_events, drill_sim):
    timeline = []
    snapshots = drill_sim.station_snapshots.all().order_by('snapshot_time')

    for event in blockade_events:
        event_entry = {
            'event_name': event.name,
            'event_type': event.get_event_type_display(),
            'start_hour': event.start_hour,
            'end_hour': event.end_hour,
            'severity': event.severity,
            'affected_snapshots': [],
        }

        for snap in snapshots:
            if event.start_hour <= snap.snapshot_time % 24.0 < event.end_hour:
                event_entry['affected_snapshots'].append({
                    'time': round(snap.snapshot_time, 2),
                    'station_code': snap.station_code,
                    'queue_length': snap.queue_length,
                    'utilization': snap.utilization,
                })

        timeline.append(event_entry)

    timeline.sort(key=lambda x: x['start_hour'])
    return timeline


def _compute_bottleneck_diff(before_result, after_result):
    before_bns = {bn['code']: bn for bn in before_result['bottleneck_list']}
    after_bns = {bn['code']: bn for bn in after_result['bottleneck_list']}

    all_codes = set(before_bns.keys()) | set(after_bns.keys())
    diff = {
        'new_bottlenecks': [],
        'resolved_bottlenecks': [],
        'worsened': [],
        'improved': [],
    }

    for code in all_codes:
        before = before_bns.get(code)
        after = after_bns.get(code)

        if after and not before:
            diff['new_bottlenecks'].append({
                'code': code,
                'name': after['name'],
                'score': after['score'],
                'avg_wait': after['avg_wait'],
            })
        elif before and not after:
            diff['resolved_bottlenecks'].append({
                'code': code,
                'name': before['name'],
                'previous_score': before['score'],
            })
        elif before and after:
            score_diff = after['score'] - before['score']
            wait_diff = after['avg_wait'] - before['avg_wait']
            entry = {
                'code': code,
                'name': after['name'],
                'before_score': before['score'],
                'after_score': after['score'],
                'score_diff': round(score_diff, 2),
                'before_wait': before['avg_wait'],
                'after_wait': after['avg_wait'],
                'wait_diff': round(wait_diff, 4),
            }
            if score_diff > 5:
                diff['worsened'].append(entry)
            elif score_diff < -5:
                diff['improved'].append(entry)

    diff['new_bottlenecks'].sort(key=lambda x: x['score'], reverse=True)
    diff['worsened'].sort(key=lambda x: x['score_diff'], reverse=True)
    diff['improved'].sort(key=lambda x: x['score_diff'])
    return diff


def _generate_recovery_strategies(blockade_events, before_result, after_result, drill):
    strategies = []

    for event in blockade_events:
        if event.event_type == 'road_blocked':
            strategies.append({
                'event': event.name,
                'type': 'road_blocked',
                'priority': 'high',
                'strategy': '紧急改道',
                'description': f'道路 {event.road} 已封锁（{event.start_hour}-{event.end_hour}时），建议立即启用备选路线绕行，预计改道成本倍率 {event.reroute_cost_multiplier}x',
                'actions': [
                    f'封锁时段 {event.start_hour}-{event.end_hour}时禁止通行',
                    f'启用备选路线，接受 {event.reroute_cost_multiplier}x 成本增加',
                    '将受影响任务优先级提升至加急',
                ],
            })

        elif event.event_type == 'road_restricted':
            strategies.append({
                'event': event.name,
                'type': 'road_restricted',
                'priority': 'medium',
                'strategy': '限流调度',
                'description': f'道路 {event.road} 限流中（通行率{event.flow_rate*100:.0f}%），建议错峰调度或部分改道',
                'actions': [
                    f'限流时段 {event.start_hour}-{event.end_hour}时仅允许 {event.flow_rate*100:.0f}% 通行',
                    '将非紧急任务延后至限流结束',
                    f'紧急任务可考虑改道，成本倍率 {event.reroute_cost_multiplier}x',
                ],
            })

        elif event.event_type == 'station_down':
            strategies.append({
                'event': event.name,
                'type': 'station_down',
                'priority': 'critical',
                'strategy': '驿站应急',
                'description': f'驿站 {event.station} 停摆（{event.start_hour}-{event.end_hour}时），所有经停任务需绕行',
                'actions': [
                    f'停摆时段 {event.start_hour}-{event.end_hour}时完全不可用',
                    '所有经停该驿站任务重新规划路线',
                    '调派邻近驿站增加处理窗口',
                    '如可能，临时开设替代驿站',
                ],
            })

        elif event.event_type == 'military_priority':
            strategies.append({
                'event': event.name,
                'type': 'military_priority',
                'priority': 'medium',
                'strategy': '军务让行',
                'description': f'军务优先通行（等级{event.military_priority_level}），普通任务需让行',
                'actions': [
                    f'军务优先时段 {event.start_hour}-{event.end_hour}时',
                    f'等级{event.military_priority_level}以下任务需排队等候',
                    '普通任务可考虑错峰或改道避让',
                ],
            })

    if drill.after_avg_wait and drill.before_avg_wait:
        wait_increase = drill.after_avg_wait - drill.before_avg_wait
        if wait_increase > 0.5:
            strategies.append({
                'event': '综合建议',
                'type': 'general',
                'priority': 'high',
                'strategy': '全局面优化',
                'description': f'封锁导致平均等待增加 {wait_increase:.2f} 时辰，建议综合施策',
                'actions': [
                    '增加热门驿站处理窗口数量',
                    '延长运营时段分散高峰压力',
                    '在关键节点增设临时中转点',
                    '优先保障高优先级任务通道畅通',
                ],
            })

    if drill.after_delay_count and drill.before_delay_count is not None:
        delay_increase = drill.after_delay_count - drill.before_delay_count
        if delay_increase > 5:
            strategies.append({
                'event': '延误控制',
                'type': 'general',
                'priority': 'high',
                'strategy': '延误缓解',
                'description': f'延误任务增加 {delay_increase} 个，需采取紧急措施',
                'actions': [
                    '对延误高风险任务提前预警',
                    '调配备用运力增援瓶颈路段',
                    '与收件方沟通调整时限预期',
                ],
            })

    strategies.sort(key=lambda x: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(x.get('priority', 'low')))
    return strategies


def get_blockade_drill_data(drill_id):
    drill = BlockadeDrill.objects.get(pk=drill_id)
    data = {
        'drill': {
            'id': drill.pk,
            'name': drill.name,
            'status': drill.status,
            'base_simulation_id': drill.base_simulation_id,
            'before_avg_wait': drill.before_avg_wait,
            'before_max_wait': drill.before_max_wait,
            'before_avg_total': drill.before_avg_total,
            'before_delay_count': drill.before_delay_count,
            'before_bottleneck_codes': drill.before_bottleneck_codes,
            'after_avg_wait': drill.after_avg_wait,
            'after_max_wait': drill.after_max_wait,
            'after_avg_total': drill.after_avg_total,
            'after_delay_count': drill.after_delay_count,
            'after_bottleneck_codes': drill.after_bottleneck_codes,
            'reroute_cost_total': drill.reroute_cost_total,
            'affected_task_count': drill.affected_task_count,
        },
        'congestion_transfer': drill.congestion_transfer,
        'impact_timeline': drill.impact_timeline,
        'bottleneck_diff': drill.bottleneck_diff,
        'recovery_strategies': drill.recovery_strategies,
        'blockade_events': [
            {
                'id': e.pk,
                'name': e.name,
                'event_type': e.get_event_type_display(),
                'start_hour': e.start_hour,
                'end_hour': e.end_hour,
                'severity': e.severity,
                'flow_rate': e.flow_rate,
                'road': str(e.road) if e.road else None,
                'station': str(e.station) if e.station else None,
            }
            for e in drill.blockade_events.all()
        ],
        'comparison': _build_comparison_chart_data(drill),
    }
    return data


def _build_comparison_chart_data(drill):
    comparison = {
        'wait_comparison': {
            'before': drill.before_avg_wait or 0,
            'after': drill.after_avg_wait or 0,
            'diff': round((drill.after_avg_wait or 0) - (drill.before_avg_wait or 0), 4),
        },
        'total_comparison': {
            'before': drill.before_avg_total or 0,
            'after': drill.after_avg_total or 0,
            'diff': round((drill.after_avg_total or 0) - (drill.before_avg_total or 0), 4),
        },
        'delay_comparison': {
            'before': drill.before_delay_count or 0,
            'after': drill.after_delay_count or 0,
            'diff': (drill.after_delay_count or 0) - (drill.before_delay_count or 0),
        },
        'max_wait_comparison': {
            'before': drill.before_max_wait or 0,
            'after': drill.after_max_wait or 0,
            'diff': round((drill.after_max_wait or 0) - (drill.before_max_wait or 0), 4),
        },
    }
    return comparison
