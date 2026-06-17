import math
import random
import heapq
from collections import defaultdict, deque
from .models import (
    Station, StationPeakHour, SimulationRun, SimTask,
    SimStationVisit, SimStationSnapshot, SimBottleneckStation,
    Road, DeliveryTask
)
from .engine import _build_graph, _dijkstra, find_path, calculate_segment_time


EVENT_TASK_ARRIVE_AT_STATION = 'arrive_station'
EVENT_STATION_PROCESS_DONE = 'process_done'
EVENT_SNAPSHOT = 'snapshot'
EVENT_TASK_FINISH = 'task_finish'


class StationQueue:
    def __init__(self, station, enable_peak_hours=True):
        self.station = station
        self.station_id = station.pk
        self.station_code = station.code
        self.window_count = station.window_count
        self.base_process_time = station.process_time
        self.queue_rule = station.queue_rule
        self.capacity = station.capacity
        self.queue = []
        self.busy_windows = 0
        self.enable_peak_hours = enable_peak_hours
        self.peak_hours = list(station.peak_hours.all()) if enable_peak_hours else []
        self._sorted_peak_hours = sorted(self.peak_hours, key=lambda x: x.start_hour)

        self.total_wait_times = []
        self.queue_length_history = []
        self.utilization_history = []
        self.visit_count = 0
        self.max_queue_length = 0
        self.peak_queue_count = 0

    def is_peak_hour_config(self, current_time):
        if not self.enable_peak_hours or not self._sorted_peak_hours:
            return None
        t = current_time % 24.0
        for ph in self._sorted_peak_hours:
            if ph.start_hour <= t < ph.end_hour:
                return ph
        return None

    def effective_windows(self, current_time):
        ph = self.is_peak_hour_config(current_time)
        if ph:
            return max(1, int(math.floor(self.window_count * ph.capacity_multiplier)))
        return self.window_count

    def effective_process_time(self, current_time, priority=1):
        base = self.base_process_time
        ph = self.is_peak_hour_config(current_time)
        if ph:
            base = base * (1 + ph.process_delay_pct / 100.0)
        priority_factor = {1: 1.0, 2: 0.8, 3: 0.6}.get(priority, 1.0)
        return max(0.01, base * priority_factor)

    def queue_sort_key(self, item):
        priority, arrival_order, sim_task_obj, visit_record = item
        if self.queue_rule == 'fifo':
            return (arrival_order,)
        elif self.queue_rule == 'priority_strict':
            return (-priority, arrival_order)
        elif self.queue_rule == 'priority_weighted':
            rand_weight = {1: 3, 2: 2, 3: 1}.get(priority, 3)
            return (rand_weight, arrival_order)
        elif self.queue_rule == 'priority_class':
            return (-priority, arrival_order)
        else:
            return (arrival_order,)

    def add_to_queue(self, priority, arrival_order, sim_task_obj, visit_record):
        item = (priority, arrival_order, sim_task_obj, visit_record)
        self.queue.append(item)
        self.queue.sort(key=self.queue_sort_key)
        self.visit_count += 1
        if len(self.queue) > self.max_queue_length:
            self.max_queue_length = len(self.queue)
        if len(self.queue) > self.effective_windows(sim_task_obj.get('current_time', 0)) * 2:
            self.peak_queue_count += 1
        return len(self.queue)

    def try_start_processing(self, current_time):
        eff_windows = self.effective_windows(current_time)
        started = []
        while self.queue and self.busy_windows < eff_windows:
            item = self.queue.pop(0)
            priority, arrival_order, sim_task_obj, visit_record = item
            self.busy_windows += 1
            started.append(item)
        return started

    def finish_processing(self):
        if self.busy_windows > 0:
            self.busy_windows -= 1

    def record_queue_length(self, current_time):
        self.queue_length_history.append((current_time, len(self.queue)))

    def record_utilization(self, current_time):
        eff_windows = self.effective_windows(current_time)
        util = (self.busy_windows / eff_windows * 100.0) if eff_windows > 0 else 0
        self.utilization_history.append((current_time, util))

    def get_stats(self):
        total_wait = sum(self.total_wait_times) if self.total_wait_times else 0
        avg_wait = total_wait / len(self.total_wait_times) if self.total_wait_times else 0
        max_wait = max(self.total_wait_times) if self.total_wait_times else 0
        avg_queue = sum(q for _, q in self.queue_length_history) / len(self.queue_length_history) if self.queue_length_history else 0
        avg_util = sum(u for _, u in self.utilization_history) / len(self.utilization_history) if self.utilization_history else 0
        return {
            'total_visits': self.visit_count,
            'total_wait_time': total_wait,
            'avg_wait_time': avg_wait,
            'max_wait_time': max_wait,
            'avg_queue_length': avg_queue,
            'max_queue_length': self.max_queue_length,
            'avg_utilization': avg_util,
            'peak_queue_count': self.peak_queue_count,
        }


class QueueSimulationEngine:
    def __init__(self, simulation_run):
        self.sim_run = simulation_run
        self.random_seed = simulation_run.random_seed
        self.sim_start = simulation_run.sim_start_time
        self.sim_end = simulation_run.sim_end_time
        self.task_count = simulation_run.task_count
        self.enable_peak_hours = simulation_run.enable_peak_hours
        self.priority_distribution = simulation_run.priority_distribution or {'1': 0.6, '2': 0.3, '3': 0.1}

        self.event_queue = []
        self.event_counter = 0
        self.global_arrival_counter = 0

        self.station_queues = {}
        for station in Station.objects.all():
            self.station_queues[station.pk] = StationQueue(station, enable_peak_hours=self.enable_peak_hours)

        self.station_id_to_code = {s.pk: s.code for s in Station.objects.all()}
        self.station_id_to_name = {s.pk: s.name for s in Station.objects.all()}

        self.sim_tasks = []
        self.all_visits = []
        self.snapshots = []

        random.seed(self.random_seed)

        self.graph = _build_graph()

    def _schedule_event(self, event_time, event_type, data):
        self.event_counter += 1
        heapq.heappush(
            self.event_queue,
            (event_time, self.event_counter, event_type, data)
        )

    def _generate_task_routes(self):
        stations = list(Station.objects.all())
        if len(stations) < 2:
            return []

        routes = []
        attempts = 0
        while len(routes) < self.task_count and attempts < self.task_count * 10:
            attempts += 1
            origin = random.choice(stations)
            dest = random.choice(stations)
            if origin.pk == dest.pk:
                continue
            result = _dijkstra(
                self.graph, origin.pk, dest.pk,
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

    def _generate_departure_times(self, routes):
        sim_duration = self.sim_end - self.sim_start
        mid_point = self.sim_start + sim_duration * 0.4

        for i, route in enumerate(routes):
            base_departure = self.sim_start + (i / max(1, len(routes))) * sim_duration * 0.8
            noise = random.uniform(-0.3, 0.5)
            dep = max(self.sim_start, min(self.sim_end - 0.5, base_departure + noise))

            if self.enable_peak_hours:
                peak_bias = random.random()
                if peak_bias < 0.35:
                    morning_peak = 8.0 + random.uniform(-1.0, 1.0)
                    dep = morning_peak % 24.0
                elif peak_bias < 0.6:
                    evening_peak = 17.0 + random.uniform(-1.0, 1.5)
                    dep = evening_peak % 24.0

            route['departure_time'] = dep

            if route['departure_time'] < self.sim_start:
                route['departure_time'] += 24.0

        routes.sort(key=lambda x: x['departure_time'])
        return routes

    def _calc_travel_time_between(self, from_station_id, to_station_id, road, priority):
        seg_result = calculate_segment_time(road, priority=priority)
        return seg_result['travel_time']

    def run(self):
        routes = self._generate_task_routes()
        if not routes:
            return {'success': False, 'error': '无法生成任务路线，请确保至少有2个连通的驿站'}

        routes = self._generate_departure_times(routes)

        sim_task_objs = []
        for idx, route in enumerate(routes):
            sim_code = f'SIM-{self.sim_run.pk:04d}-{idx + 1:04d}'
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

                sq = self.station_queues[to_station_id]
                self.global_arrival_counter += 1
                arrival_order = self.global_arrival_counter

                visit_record = {
                    'station_id': to_station_id,
                    'station_code': sq.station_code,
                    'visit_order': station_idx + (0 if is_depart_from_origin else 1),
                    'arrive_time': round(current_time, 3),
                    'in_peak_hour': sq.is_peak_hour_config(current_time) is not None,
                    'queue_position_on_arrival': len(sq.queue),
                }

                if is_depart_from_origin and to_station_id == sim_task_obj['origin_id']:
                    pass
                else:
                    pass

                eff_process = sq.effective_process_time(current_time, sim_task_obj['priority'])
                travel_next = 0.0
                if station_idx < len(path_roads):
                    next_road = path_roads[station_idx]
                    if not is_depart_from_origin and station_idx > 0:
                        pass
                    else:
                        travel_next = self._calc_travel_time_between(
                            next_road.from_station_id,
                            next_road.to_station_id,
                            next_road,
                            sim_task_obj['priority']
                        )
                        sim_task_obj['expected_total_no_congestion'] += travel_next + eff_process

                queue_pos = sq.add_to_queue(
                    sim_task_obj['priority'], arrival_order, sim_task_obj, visit_record)
                visit_record['queue_enter_time'] = round(current_time, 3)

                started_items = sq.try_start_processing(current_time)
                for s_item in started_items:
                    s_priority, s_order, s_task_obj, s_visit = s_item
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
                self.all_visits.append((sim_task_obj, visit_record))

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
                    ns_priority, ns_order, ns_task_obj, ns_visit = ns_item
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

    def _save_results(self, completed_tasks):
        from django.utils import timezone

        all_wait_times = []
        all_total_times = []
        delay_count = 0

        sim_task_records = []
        for sim_task_obj in completed_tasks:
            total_wait = sum(v['wait_duration'] for v in sim_task_obj['visits'])
            max_wait = max((v['wait_duration'] for v in sim_task_obj['visits']), default=0)
            total_time = sim_task_obj['arrival_time'] - sim_task_obj['departure_time']
            expected = sim_task_obj.get('expected_total_no_congestion', total_time)
            delay = max(0, total_time - expected)
            is_delayed = delay > 0.01

            all_wait_times.append(total_wait)
            all_total_times.append(total_time)
            if is_delayed:
                delay_count += 1

            db_sim_task = SimTask(
                simulation=self.sim_run,
                sim_task_code=sim_task_obj['sim_task_code'],
                origin_id=sim_task_obj['origin_id'],
                destination_id=sim_task_obj['destination_id'],
                priority=sim_task_obj['priority'],
                departure_time=sim_task_obj['departure_time'],
                arrival_time=sim_task_obj['arrival_time'],
                expected_time=round(expected, 3),
                total_wait_time=round(total_wait, 3),
                max_wait_at_station=round(max_wait, 3),
                station_count=len(sim_task_obj['path_roads']),
                is_delayed=is_delayed,
                delay_minutes=round(delay, 3),
            )
            sim_task_records.append(db_sim_task)

        SimTask.objects.bulk_create(sim_task_records)

        sim_task_map = {st.sim_task_code: st for st in sim_task_records}

        visit_records = []
        for sim_task_obj in completed_tasks:
            db_st = sim_task_map.get(sim_task_obj['sim_task_code'])
            if not db_st:
                continue
            for v in sim_task_obj['visits']:
                visit_records.append(SimStationVisit(
                    sim_task=db_st,
                    station_id=v['station_id'],
                    station_code=v['station_code'],
                    visit_order=v['visit_order'],
                    arrive_time=v.get('arrive_time'),
                    queue_enter_time=v.get('queue_enter_time'),
                    process_start_time=v.get('process_start_time'),
                    process_end_time=v.get('process_end_time'),
                    depart_time=v.get('depart_time'),
                    wait_duration=v.get('wait_duration', 0),
                    process_duration=v.get('process_duration', 0),
                    queue_position_on_arrival=v.get('queue_position_on_arrival', 0),
                    in_peak_hour=v.get('in_peak_hour', False),
                ))
        SimStationVisit.objects.bulk_create(visit_records)

        snapshot_records = []
        for snap in self.snapshots:
            snapshot_records.append(SimStationSnapshot(
                simulation=self.sim_run,
                station_id=snap['station_id'],
                station_code=snap['station_code'],
                snapshot_time=snap['snapshot_time'],
                queue_length=snap['queue_length'],
                busy_windows=snap['busy_windows'],
                total_windows=snap['total_windows'],
                utilization=snap['utilization'],
                in_peak_hour=snap['in_peak_hour'],
            ))
        SimStationSnapshot.objects.bulk_create(snapshot_records)

        bottleneck_data = []
        for sid, sq in self.station_queues.items():
            stats = sq.get_stats()
            if stats['total_visits'] == 0:
                continue
            score = (
                stats['avg_wait_time'] * 10 +
                stats['max_wait_time'] * 5 +
                stats['avg_queue_length'] * 3 +
                stats['avg_utilization'] * 0.1 +
                stats['peak_queue_count'] * 2
            )
            bottleneck_data.append({
                'station_id': sid,
                'station_code': sq.station_code,
                'station_name': self.station_id_to_name.get(sid, ''),
                'stats': stats,
                'score': score,
            })

        bottleneck_data.sort(key=lambda x: x['score'], reverse=True)
        bottleneck_records = []
        for rank, bd in enumerate(bottleneck_data, 1):
            bottleneck_records.append(SimBottleneckStation(
                simulation=self.sim_run,
                station_id=bd['station_id'],
                station_code=bd['station_code'],
                station_name=bd['station_name'],
                total_visits=bd['stats']['total_visits'],
                avg_wait_time=round(bd['stats']['avg_wait_time'], 4),
                max_wait_time=round(bd['stats']['max_wait_time'], 4),
                total_wait_time=round(bd['stats']['total_wait_time'], 4),
                avg_queue_length=round(bd['stats']['avg_queue_length'], 4),
                max_queue_length=bd['stats']['max_queue_length'],
                avg_utilization=round(bd['stats']['avg_utilization'], 2),
                peak_queue_count=bd['stats']['peak_queue_count'],
                bottleneck_score=round(bd['score'], 2),
                rank=rank,
            ))
        SimBottleneckStation.objects.bulk_create(bottleneck_records)

        self.sim_run.total_tasks_simulated = len(completed_tasks)
        if all_wait_times:
            self.sim_run.avg_wait_time = round(sum(all_wait_times) / len(all_wait_times), 4)
            self.sim_run.max_wait_time = round(max(all_wait_times), 4)
        if all_total_times:
            self.sim_run.avg_total_time = round(sum(all_total_times) / len(all_total_times), 4)
        self.sim_run.total_delay_count = delay_count
        self.sim_run.status = 'completed'
        self.sim_run.finished_at = timezone.now()
        self.sim_run.save()


def run_simulation(simulation_run_id):
    from django.utils import timezone
    sim_run = SimulationRun.objects.get(pk=simulation_run_id)
    sim_run.status = 'running'
    sim_run.save()

    try:
        engine = QueueSimulationEngine(sim_run)
        result = engine.run()
        if not result['success']:
            sim_run.status = 'failed'
            sim_run.error_message = result.get('error', '未知错误')
            sim_run.finished_at = timezone.now()
            sim_run.save()
            return result
        return result
    except Exception as e:
        sim_run.status = 'failed'
        sim_run.error_message = str(e)
        sim_run.finished_at = timezone.now()
        sim_run.save()
        return {'success': False, 'error': str(e)}


def get_simulation_result_data(sim_run_id):
    sim_run = SimulationRun.objects.get(pk=sim_run_id)

    sim_tasks_qs = sim_run.sim_tasks.all()
    task_wait_list = []
    delay_data = []
    for st in sim_tasks_qs:
        task_wait_list.append({
            'code': st.sim_task_code,
            'priority': st.priority,
            'total_wait': st.total_wait_time,
            'max_wait': st.max_wait_at_station,
            'total_time': (st.arrival_time or 0) - st.departure_time,
            'expected': st.expected_time or 0,
            'delay': st.delay_minutes,
            'is_delayed': st.is_delayed,
        })

    heatmap_data = []
    snapshots = sim_run.station_snapshots.all().order_by('snapshot_time')
    station_times = defaultdict(list)
    station_utils = defaultdict(list)
    for snap in snapshots:
        station_times[snap.station_code].append((snap.snapshot_time, snap.queue_length))
        station_utils[snap.station_code].append((snap.utilization))

    heatmap = {}
    for code, time_q in station_times.items():
        heatmap[code] = [q for _, q in time_q]

    time_labels = []
    if snapshots:
        min_t = min(s.snapshot_time for s in snapshots)
        max_t = max(s.snapshot_time for s in snapshots)
        step = max(0.5, (max_t - min_t) / 20)
        t = min_t
        while t <= max_t:
            time_labels.append(round(t, 1))
            t += step

    bottleneck_qs = sim_run.bottleneck_stations.all().order_by('rank')
    bottleneck_list = []
    for bn in bottleneck_qs:
        bottleneck_list.append({
            'rank': bn.rank,
            'code': bn.station_code,
            'name': bn.station_name,
            'total_visits': bn.total_visits,
            'avg_wait': bn.avg_wait_time,
            'max_wait': bn.max_wait_time,
            'avg_queue': bn.avg_queue_length,
            'max_queue': bn.max_queue_length,
            'avg_util': bn.avg_utilization,
            'score': bn.bottleneck_score,
        })

    total_tasks_count = sim_tasks_qs.count()
    priority_stats = defaultdict(lambda: {'count': 0, 'total_wait': 0, 'delayed': 0})
    for st in sim_tasks_qs:
        key = str(st.priority)
        priority_stats[key]['count'] += 1
        priority_stats[key]['total_wait'] += st.total_wait_time
        if st.is_delayed:
            priority_stats[key]['delayed'] += 1

    priority_analysis = []
    priority_labels = {1: '普通', 2: '加急', 3: '八百里加急'}
    for p_key in sorted(priority_stats.keys()):
        ps = priority_stats[p_key]
        avg_w = ps['total_wait'] / ps['count'] if ps['count'] > 0 else 0
        priority_analysis.append({
            'priority': priority_labels.get(int(p_key), p_key),
            'count': ps['count'],
            'avg_wait': round(avg_w, 4),
            'delayed': ps['delayed'],
            'delay_rate': round(ps['delayed'] / max(1, ps['count']) * 100, 2),
        })

    time_fluctuation = []
    if sim_tasks_qs.exists():
        sim_start = sim_run.sim_start_time
        sim_end = sim_run.sim_end_time
        bucket_size = max(0.5, (sim_end - sim_start) / 12)
        buckets = defaultdict(lambda: {'count': 0, 'total': 0, 'expected': 0})
        for st in sim_tasks_qs:
            bucket_idx = int((st.departure_time - sim_start) / bucket_size)
            bucket_key = sim_start + bucket_idx * bucket_size
            buckets[bucket_key]['count'] += 1
            total = (st.arrival_time or st.departure_time) - st.departure_time
            buckets[bucket_key]['total'] += total
            buckets[bucket_key]['expected'] += st.expected_time or total

        sorted_buckets = sorted(buckets.items())
        for bk, bv in sorted_buckets:
            avg_total = bv['total'] / bv['count'] if bv['count'] > 0 else 0
            avg_expected = bv['expected'] / bv['count'] if bv['count'] > 0 else 0
            time_fluctuation.append({
                'time': round(bk, 1),
                'count': bv['count'],
                'avg_total': round(avg_total, 4),
                'avg_expected': round(avg_expected, 4),
                'fluctuation': round((avg_total - avg_expected) / max(0.01, avg_expected) * 100, 2),
            })

    return {
        'sim_run': sim_run,
        'task_wait_list': task_wait_list,
        'heatmap_data': heatmap,
        'time_labels': time_labels,
        'station_codes': list(heatmap.keys()),
        'bottleneck_list': bottleneck_list,
        'priority_analysis': priority_analysis,
        'time_fluctuation': time_fluctuation,
    }
