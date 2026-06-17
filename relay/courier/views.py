import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q
from .models import (
    Station, Road, HorseChangeStrategy, WeatherRecord,
    DeliveryTask, DeliverySegment, DeliveryPlan, PlanSegment,
    SimulationRun, SimTask, SimStationVisit, SimBottleneckStation, StationPeakHour,
)
from .forms import (
    StationForm, RoadForm, HorseChangeStrategyForm,
    WeatherRecordForm, DeliveryTaskForm, DeliveryTaskStatusForm,
    DeliverySegmentForm, SimulationRunForm, StationPeakHourForm,
)
from .engine import (
    calculate_delivery_time, recalculate_affected_tasks,
    get_analysis_data, find_path, calculate_segment_time,
    generate_all_plans, get_plan_comparison_data, get_gantt_data,
    find_all_paths,
)
from .simulation_engine import run_simulation, get_simulation_result_data


def index(request):
    station_count = Station.objects.count()
    road_count = Road.objects.count()
    task_count = DeliveryTask.objects.count()
    strategy_count = HorseChangeStrategy.objects.count()
    delayed_warning_count = DeliveryTask.objects.filter(delay_warning=True).count()
    high_risk_count = DeliveryTask.objects.filter(has_high_risk=True).count()
    return render(request, 'courier/index.html', {
        'station_count': station_count,
        'road_count': road_count,
        'task_count': task_count,
        'strategy_count': strategy_count,
        'delayed_warning_count': delayed_warning_count,
        'high_risk_count': high_risk_count,
    })


def station_list(request):
    stations = Station.objects.all()
    return render(request, 'courier/station_list.html', {'stations': stations})


def station_create(request):
    if request.method == 'POST':
        form = StationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '驿站创建成功')
            return redirect('courier:station_list')
    else:
        form = StationForm()
    return render(request, 'courier/station_form.html', {'form': form, 'title': '新建驿站'})


def station_update(request, pk):
    station = get_object_or_404(Station, pk=pk)
    if request.method == 'POST':
        form = StationForm(request.POST, instance=station)
        if form.is_valid():
            form.save()
            messages.success(request, '驿站更新成功')
            return redirect('courier:station_list')
    else:
        form = StationForm(instance=station)
    return render(request, 'courier/station_form.html', {'form': form, 'title': '编辑驿站'})


def station_delete(request, pk):
    station = get_object_or_404(Station, pk=pk)
    if request.method == 'POST':
        station.delete()
        messages.success(request, '驿站已删除')
        return redirect('courier:station_list')
    return render(request, 'courier/station_confirm_delete.html', {'station': station})


def road_list(request):
    roads = Road.objects.select_related('from_station', 'to_station').all()
    return render(request, 'courier/road_list.html', {'roads': roads})


def road_create(request):
    if request.method == 'POST':
        form = RoadForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '道路创建成功')
            return redirect('courier:road_list')
    else:
        form = RoadForm()
    return render(request, 'courier/road_form.html', {'form': form, 'title': '新建道路'})


def road_update(request, pk):
    road = get_object_or_404(Road, pk=pk)
    if request.method == 'POST':
        form = RoadForm(request.POST, instance=road)
        if form.is_valid():
            form.save()
            recalculate_affected_tasks(road.pk)
            messages.success(request, '道路更新成功，已重新计算相关任务')
            return redirect('courier:road_list')
    else:
        form = RoadForm(instance=road)
    return render(request, 'courier/road_form.html', {'form': form, 'title': '编辑道路'})


def road_delete(request, pk):
    road = get_object_or_404(Road, pk=pk)
    affected_task_ids = list(
        DeliverySegment.objects.filter(road_id=pk).values_list('task_id', flat=True).distinct()
    )
    if request.method == 'POST':
        road.delete()
        for task_id in affected_task_ids:
            try:
                task = DeliveryTask.objects.get(pk=task_id)
                calculate_delivery_time(task, force_recalculate=True)
                if task.status == 'executable':
                    task.status = 'draft'
                    task.save()
            except DeliveryTask.DoesNotExist:
                pass
        if affected_task_ids:
            messages.warning(request, f'道路已删除，已重新计算 {len(affected_task_ids)} 个相关任务，可执行任务已重置为草稿')
        else:
            messages.success(request, '道路已删除')
        return redirect('courier:road_list')
    return render(request, 'courier/road_confirm_delete.html', {'road': road, 'affected_count': len(affected_task_ids)})


def strategy_list(request):
    strategies = HorseChangeStrategy.objects.all()
    return render(request, 'courier/strategy_list.html', {'strategies': strategies})


def strategy_create(request):
    if request.method == 'POST':
        form = HorseChangeStrategyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '换马策略创建成功')
            return redirect('courier:strategy_list')
    else:
        form = HorseChangeStrategyForm()
    return render(request, 'courier/strategy_form.html', {'form': form, 'title': '新建换马策略'})


def strategy_update(request, pk):
    strategy = get_object_or_404(HorseChangeStrategy, pk=pk)
    if request.method == 'POST':
        form = HorseChangeStrategyForm(request.POST, instance=strategy)
        if form.is_valid():
            form.save()
            messages.success(request, '换马策略更新成功')
            return redirect('courier:strategy_list')
    else:
        form = HorseChangeStrategyForm(instance=strategy)
    return render(request, 'courier/strategy_form.html', {'form': form, 'title': '编辑换马策略'})


def strategy_delete(request, pk):
    strategy = get_object_or_404(HorseChangeStrategy, pk=pk)
    if request.method == 'POST':
        strategy.delete()
        messages.success(request, '换马策略已删除')
        return redirect('courier:strategy_list')
    return render(request, 'courier/strategy_confirm_delete.html', {'strategy': strategy})


def weather_list(request):
    weather_records = WeatherRecord.objects.select_related('road', 'road__from_station', 'road__to_station').all()
    latest_per_road = {}
    for record in weather_records:
        if record.road_id not in latest_per_road:
            latest_per_road[record.road_id] = record.pk
        record.is_latest = (record.pk == latest_per_road[record.road_id])
    return render(request, 'courier/weather_list.html', {'weather_records': weather_records})


def weather_create(request):
    if request.method == 'POST':
        form = WeatherRecordForm(request.POST)
        if form.is_valid():
            weather = form.save()
            recalculate_affected_tasks(weather.road_id)
            messages.success(request, '天气记录创建成功，已重新计算相关任务送达时间')
            return redirect('courier:weather_list')
    else:
        form = WeatherRecordForm()
    return render(request, 'courier/weather_form.html', {'form': form, 'title': '新建天气记录'})


def weather_update(request, pk):
    weather = get_object_or_404(WeatherRecord, pk=pk)
    old_road_id = weather.road_id
    if request.method == 'POST':
        form = WeatherRecordForm(request.POST, instance=weather)
        if form.is_valid():
            weather = form.save(commit=False)
            from django.utils import timezone
            weather.recorded_at = timezone.now()
            weather.save()
            recalculate_affected_tasks(weather.road_id)
            if old_road_id != weather.road_id:
                recalculate_affected_tasks(old_road_id)
            messages.success(request, '天气记录更新成功，预计送达时间已重新计算')
            return redirect('courier:weather_list')
    else:
        form = WeatherRecordForm(instance=weather)
    return render(request, 'courier/weather_form.html', {'form': form, 'title': '编辑天气记录'})


def weather_delete(request, pk):
    weather = get_object_or_404(WeatherRecord, pk=pk)
    road_id = weather.road_id
    if request.method == 'POST':
        weather.delete()
        recalculate_affected_tasks(road_id)
        messages.success(request, '天气记录已删除，预计送达时间已重新计算')
        return redirect('courier:weather_list')
    return render(request, 'courier/weather_confirm_delete.html', {'weather': weather})


def task_list(request):
    tasks = DeliveryTask.objects.select_related('origin', 'destination', 'strategy').all()
    return render(request, 'courier/task_list.html', {'tasks': tasks})


def task_create(request):
    if request.method == 'POST':
        form = DeliveryTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            path = find_path(task.origin_id, task.destination_id)
            if not path:
                messages.error(request, '起点与终点之间没有连通路线，不能创建递送任务')
                return render(request, 'courier/task_form.html', {'form': form, 'title': '新建递送任务'})

            task.save()
            calculate_delivery_time(task, force_recalculate=True)
            msg = f'递送任务创建成功，预计送达时间：{task.estimated_hours}时辰'
            if task.delay_warning:
                messages.warning(request, msg + ' 【延误预警】该任务存在延误风险！')
            else:
                messages.success(request, msg)
            return redirect('courier:task_detail', pk=task.pk)
    else:
        form = DeliveryTaskForm()
    return render(request, 'courier/task_form.html', {'form': form, 'title': '新建递送任务'})


def task_detail(request, pk):
    task = get_object_or_404(DeliveryTask, pk=pk)
    segments = task.segments.select_related('road', 'road__from_station', 'road__to_station', 'override_strategy').all()

    segment_details = []
    segment_forms = []
    for seg in segments:
        road = seg.road
        result = calculate_segment_time(
            road=road, priority=task.priority, strategy=task.strategy, segment=seg
        )
        segment_details.append({
            'segment': seg,
            'detail': result,
        })
        if request.method == 'GET':
            segment_forms.append(DeliverySegmentForm(instance=seg, prefix=f'seg_{seg.pk}'))

    chart_data = get_analysis_data(task)
    plan_comparison = get_plan_comparison_data(task)
    gantt_data = get_gantt_data(task)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'select_plan':
            plan_type = request.POST.get('plan_type')
            if plan_type in dict(DeliveryTask.PLAN_TYPE_CHOICES):
                task.selected_plan_type = plan_type
                task.save()
                calculate_delivery_time(task, force_recalculate=True)
                messages.success(request, f'已切换为「{task.get_selected_plan_type_display()}」方案')
                return redirect('courier:task_detail', pk=task.pk)
        elif action == 'update_segments':
            all_valid = True
            for seg in segments:
                form = DeliverySegmentForm(request.POST, instance=seg, prefix=f'seg_{seg.pk}')
                if form.is_valid():
                    form.save()
                else:
                    all_valid = False
            if all_valid:
                calculate_delivery_time(task, force_recalculate=True)
                messages.success(request, '路段独立配置已更新，已重新计算送达时间')
            else:
                messages.error(request, '配置有误，请检查')
            return redirect('courier:task_detail', pk=task.pk)

    context = {
        'task': task,
        'segments': segments,
        'segment_details': segment_details,
        'segment_forms': segment_forms,
        'segment_details_zip': list(zip(segment_details, segment_forms)),
        'chart_data': json.dumps(chart_data, ensure_ascii=False),
        'plan_comparison': json.dumps(plan_comparison, ensure_ascii=False),
        'gantt_data': json.dumps(gantt_data, ensure_ascii=False),
        'plans': task.plans.select_related().all(),
    }
    return render(request, 'courier/task_detail.html', context)


def task_update_status(request, pk):
    task = get_object_or_404(DeliveryTask, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status == 'executable' and task.has_high_risk:
            messages.error(request, '存在高风险断点，不能标记任务为可执行')
            return redirect('courier:task_detail', pk=task.pk)

        task.status = new_status
        task.save()
        messages.success(request, f'任务状态已更新为：{task.get_status_display()}')
        return redirect('courier:task_detail', pk=task.pk)
    return redirect('courier:task_detail', pk=task.pk)


def task_delete(request, pk):
    task = get_object_or_404(DeliveryTask, pk=pk)
    if request.method == 'POST':
        task.delete()
        messages.success(request, '递送任务已删除')
        return redirect('courier:task_list')
    return render(request, 'courier/task_confirm_delete.html', {'task': task})


def task_recalculate(request, pk):
    task = get_object_or_404(DeliveryTask, pk=pk)
    calculate_delivery_time(task, force_recalculate=True)
    msg = f'已重新计算，预计送达时间：{task.estimated_hours}时辰'
    if task.delay_warning:
        messages.warning(request, msg + ' 【延误预警】存在延误风险！')
    else:
        messages.success(request, msg)
    return redirect('courier:task_detail', pk=task.pk)


def map_view(request):
    stations = Station.objects.all()
    roads = Road.objects.select_related('from_station', 'to_station').all()
    weather_records = WeatherRecord.objects.select_related('road').all()

    stations_json = json.dumps([
        {
            'id': s.pk,
            'code': s.code,
            'name': s.name,
            'lat': s.latitude,
            'lng': s.longitude,
            'capacity': s.capacity,
            'process_time': s.process_time,
        }
        for s in stations
    ], ensure_ascii=False)

    roads_json = json.dumps([
        {
            'id': r.pk,
            'from': {'lat': r.from_station.latitude, 'lng': r.from_station.longitude, 'code': r.from_station.code},
            'to': {'lat': r.to_station.latitude, 'lng': r.to_station.longitude, 'code': r.to_station.code},
            'distance': r.distance,
            'grade': r.grade,
            'grade_display': r.get_grade_display(),
            'slope': r.slope,
        }
        for r in roads
    ], ensure_ascii=False)

    weather_map = {}
    for w in weather_records:
        weather_map[w.road_id] = {
            'type': w.weather_type,
            'display': w.get_weather_type_display(),
            'factor': w.speed_factor,
        }
    weather_json = json.dumps(weather_map, ensure_ascii=False)

    return render(request, 'courier/map.html', {
        'stations_json': stations_json,
        'roads_json': roads_json,
        'weather_json': weather_json,
    })


def analysis_dashboard(request):
    tasks = DeliveryTask.objects.select_related('origin', 'destination', 'strategy').all()
    task_data = []
    for task in tasks:
        if task.estimated_hours:
            chart = get_analysis_data(task)
            plan_comparison = get_plan_comparison_data(task)
            task_data.append({
                'task': task,
                'chart_data': json.dumps(chart, ensure_ascii=False),
                'plan_comparison': json.dumps(plan_comparison, ensure_ascii=False),
            })

    all_strategies = HorseChangeStrategy.objects.all()
    comparison_data = []
    if all_strategies.count() >= 2 and tasks.exists():
        sample_task = tasks.first()
        if sample_task:
            for strategy in all_strategies:
                segments = DeliverySegment.objects.filter(task=sample_task).select_related('road').all()
                total = 0
                for seg in segments:
                    result = calculate_segment_time(seg.road, priority=sample_task.priority, strategy=strategy)
                    total += result['total_time']
                comparison_data.append({
                    'name': strategy.name,
                    'time': round(total, 2),
                })

    delay_warning_tasks = DeliveryTask.objects.filter(delay_warning=True).select_related('origin', 'destination')
    delay_data = []
    for t in delay_warning_tasks:
        plans = t.plans.all()
        min_time = min((p.total_time for p in plans), default=t.estimated_hours or 0)
        delay_data.append({
            'task_code': t.task_code,
            'route': f'{t.origin.code}→{t.destination.code}',
            'estimated': t.estimated_hours,
            'deadline': t.deadline_hours,
            'fastest': min_time,
            'plans_count': plans.count(),
        })

    context = {
        'task_data': task_data,
        'comparison_data': json.dumps(comparison_data, ensure_ascii=False),
        'comparison_available': len(comparison_data) >= 2,
        'delay_data': json.dumps(delay_data, ensure_ascii=False),
        'delay_count': len(delay_data),
    }
    return render(request, 'courier/analysis.html', context)


def api_stations(request):
    stations = Station.objects.all()
    data = [
        {'id': s.pk, 'code': s.code, 'name': s.name, 'lat': s.latitude, 'lng': s.longitude,
         'capacity': s.capacity, 'process_time': s.process_time}
        for s in stations
    ]
    return JsonResponse(data, safe=False)


def api_roads(request):
    roads = Road.objects.select_related('from_station', 'to_station').all()
    data = [
        {
            'id': r.pk,
            'from_id': r.from_station_id,
            'to_id': r.to_station_id,
            'from_code': r.from_station.code,
            'to_code': r.to_station.code,
            'distance': r.distance,
            'grade': r.grade,
            'slope': r.slope,
        }
        for r in roads
    ]
    return JsonResponse(data, safe=False)


def api_strategies(request):
    strategies = HorseChangeStrategy.objects.all()
    data = [
        {'id': s.pk, 'name': s.name, 'interval_distance': s.interval_distance, 'change_time': s.change_time}
        for s in strategies
    ]
    return JsonResponse(data, safe=False)


def api_create_road(request):
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持 POST 请求'}, status=405)

    import json
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的 JSON 数据'}, status=400)

    from_station_id = body.get('from_station')
    to_station_id = body.get('to_station')
    distance = body.get('distance')
    slope = body.get('slope', 0)
    grade = body.get('grade', 2)

    if not from_station_id or not to_station_id:
        return JsonResponse({'error': '需要指定起点和终点驿站'}, status=400)

    if not distance or float(distance) <= 0:
        return JsonResponse({'error': '道路长度必须大于0'}, status=400)

    if from_station_id == to_station_id:
        return JsonResponse({'error': '起点和终点不能相同'}, status=400)

    if Road.objects.filter(from_station_id=from_station_id, to_station_id=to_station_id).exists():
        return JsonResponse({'error': '该道路已存在'}, status=400)

    try:
        from_station = Station.objects.get(pk=from_station_id)
        to_station = Station.objects.get(pk=to_station_id)
    except Station.DoesNotExist:
        return JsonResponse({'error': '驿站不存在'}, status=404)

    road = Road.objects.create(
        from_station=from_station,
        to_station=to_station,
        distance=float(distance),
        slope=float(slope),
        grade=int(grade),
    )

    WeatherRecord.objects.create(road=road, weather_type=1)

    return JsonResponse({
        'id': road.pk,
        'from': {'code': from_station.code, 'name': from_station.name},
        'to': {'code': to_station.code, 'name': to_station.name},
        'distance': road.distance,
        'slope': road.slope,
        'grade': road.grade,
        'grade_display': road.get_grade_display(),
    })


def api_calculate_route(request):
    origin_id = request.GET.get('origin')
    dest_id = request.GET.get('destination')
    strategy_id = request.GET.get('strategy')
    priority = int(request.GET.get('priority', 1))
    deadline = request.GET.get('deadline')
    plan_type = request.GET.get('plan_type', 'fastest')

    if not origin_id or not dest_id:
        return JsonResponse({'error': '需要指定起点和终点'}, status=400)

    all_results = find_all_paths(int(origin_id), int(dest_id), priority=priority)
    if not all_results:
        return JsonResponse({'error': '没有连通路线'}, status=404)

    strategy = None
    if strategy_id:
        strategy = HorseChangeStrategy.objects.filter(pk=int(strategy_id)).first()

    plans_output = []
    for ptype, path_roads, path_results_data in all_results:
        total_time = 0.0
        total_distance = 0.0
        risk_count = 0
        segments = []
        for idx, (road, seg_result) in enumerate(zip(path_roads, path_results_data)):
            seg_time = calculate_segment_time(road, priority=priority, strategy=strategy)
            total_time += seg_time['total_time']
            total_distance += seg_time['distance']
            if seg_time['is_high_risk']:
                risk_count += 1
            segments.append({
                'order': idx + 1,
                'from': road.from_station.code,
                'to': road.to_station.code,
                'distance': seg_time['distance'],
                'time': seg_time['total_time'],
                'travel_time': seg_time['travel_time'],
                'horse_change_time': seg_time['horse_change_time'],
                'process_time': seg_time['process_time'],
                'is_high_risk': seg_time['is_high_risk'],
                'grade': road.grade,
                'slope': road.slope,
            })

        delay_prob = 0.0
        is_delay_risk = False
        if deadline:
            try:
                dh = float(deadline)
                ratio = total_time / dh
                base_prob = max(0.0, (ratio - 0.7) / 0.5)
                risk_factor = min(1.0, risk_count * 0.15 + len(path_roads) * 0.02)
                delay_prob = min(1.0, base_prob * 0.6 + risk_factor * 0.4)
                is_delay_risk = delay_prob >= 0.3
            except (ValueError, TypeError):
                pass

        plans_output.append({
            'plan_type': ptype,
            'plan_type_display': dict(DeliveryPlan.PLAN_TYPE_CHOICES).get(ptype, ptype),
            'total_time': round(total_time, 2),
            'total_distance': round(total_distance, 2),
            'risk_count': risk_count,
            'station_count': len(path_roads),
            'is_delay_risk': is_delay_risk,
            'delay_probability': round(delay_prob, 2),
            'segments': segments,
        })

    selected = next((p for p in plans_output if p['plan_type'] == plan_type), plans_output[0] if plans_output else None)

    return JsonResponse({
        'selected_plan': selected,
        'all_plans': plans_output,
        'has_high_risk': any(p['risk_count'] > 0 for p in plans_output),
        'has_delay_risk': any(p['is_delay_risk'] for p in plans_output),
    })


def api_task_plans(request, pk):
    task = get_object_or_404(DeliveryTask, pk=pk)
    plans = generate_all_plans(task)
    comparison = get_plan_comparison_data(task)
    gantt = get_gantt_data(task)
    return JsonResponse({
        'task_code': task.task_code,
        'selected_plan_type': task.selected_plan_type,
        'plans': comparison,
        'gantt': gantt,
    })


def api_segment_config(request, task_pk, segment_pk):
    task = get_object_or_404(DeliveryTask, pk=task_pk)
    segment = get_object_or_404(DeliverySegment, pk=segment_pk, task_id=task_pk)

    if request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': '无效的 JSON 数据'}, status=400)

        form = DeliverySegmentForm(body, instance=segment)
        if form.is_valid():
            form.save()
            calculate_delivery_time(task, force_recalculate=True)
            return JsonResponse({
                'success': True,
                'estimated_hours': task.estimated_hours,
                'delay_warning': task.delay_warning,
            })
        else:
            return JsonResponse({'error': form.errors}, status=400)

    return JsonResponse({
        'segment_id': segment.pk,
        'override_strategy_id': segment.override_strategy_id,
        'override_weather': segment.override_weather,
        'departure_time': segment.departure_time,
        'segment_time': segment.segment_time,
    })


def simulation_list(request):
    simulations = SimulationRun.objects.all().order_by('-created_at')
    count_completed = SimulationRun.objects.filter(status='completed').count()
    count_running = SimulationRun.objects.filter(status='running').count()
    count_failed = SimulationRun.objects.filter(status='failed').count()
    return render(request, 'courier/simulation_list.html', {
        'simulations': simulations,
        'count_completed': count_completed,
        'count_running': count_running,
        'count_failed': count_failed,
    })


def simulation_create(request):
    if request.method == 'POST':
        form = SimulationRunForm(request.POST)
        if form.is_valid():
            sim = form.save()
            messages.success(request, f'仿真配置「{sim.name}」已创建')
            return redirect('courier:simulation_detail', pk=sim.pk)
    else:
        form = SimulationRunForm()
    return render(request, 'courier/simulation_form.html', {'form': form, 'title': '新建仿真配置'})


def simulation_detail(request, pk):
    sim = get_object_or_404(SimulationRun, pk=pk)
    context = {
        'sim': sim,
        'peak_hours': StationPeakHour.objects.select_related('station').all(),
    }
    if sim.status == 'completed':
        result_data = get_simulation_result_data(pk)
        context.update({
            'task_wait_list_json': json.dumps(result_data['task_wait_list'], ensure_ascii=False),
            'heatmap_data_json': json.dumps(result_data['heatmap_data'], ensure_ascii=False),
            'time_labels_json': json.dumps(result_data['time_labels'], ensure_ascii=False),
            'station_codes_json': json.dumps(result_data['station_codes'], ensure_ascii=False),
            'bottleneck_list_json': json.dumps(result_data['bottleneck_list'], ensure_ascii=False),
            'priority_analysis_json': json.dumps(result_data['priority_analysis'], ensure_ascii=False),
            'time_fluctuation_json': json.dumps(result_data['time_fluctuation'], ensure_ascii=False),
            'bottleneck_list': result_data['bottleneck_list'],
            'priority_analysis': result_data['priority_analysis'],
        })
    return render(request, 'courier/simulation_detail.html', context)


def simulation_run(request, pk):
    sim = get_object_or_404(SimulationRun, pk=pk)
    if sim.status == 'running':
        messages.warning(request, '该仿真正在运行中，请稍候')
        return redirect('courier:simulation_detail', pk=pk)

    sim.sim_tasks.all().delete()
    sim.bottleneck_stations.all().delete()
    sim.station_snapshots.all().delete()

    result = run_simulation(pk)
    if result['success']:
        messages.success(
            request,
            f'仿真运行完成！共 {result["completed_tasks"]}/{result["total_tasks"]} 个任务完成递送'
        )
    else:
        messages.error(request, f'仿真运行失败：{result.get("error", "未知错误")}')
    return redirect('courier:simulation_detail', pk=pk)


def simulation_delete(request, pk):
    sim = get_object_or_404(SimulationRun, pk=pk)
    if request.method == 'POST':
        sim.delete()
        messages.success(request, '仿真配置已删除')
        return redirect('courier:simulation_list')
    return render(request, 'courier/simulation_confirm_delete.html', {'sim': sim})


def peak_hour_list(request):
    peak_hours = StationPeakHour.objects.select_related('station').all()
    return render(request, 'courier/peak_hour_list.html', {'peak_hours': peak_hours})


def peak_hour_create(request):
    if request.method == 'POST':
        form = StationPeakHourForm(request.POST)
        if form.is_valid():
            ph = form.save()
            messages.success(request, f'高峰时段配置已创建：{ph}')
            return redirect('courier:peak_hour_list')
    else:
        form = StationPeakHourForm()
    return render(request, 'courier/peak_hour_form.html', {'form': form, 'title': '新建高峰时段'})


def peak_hour_update(request, pk):
    ph = get_object_or_404(StationPeakHour, pk=pk)
    if request.method == 'POST':
        form = StationPeakHourForm(request.POST, instance=ph)
        if form.is_valid():
            form.save()
            messages.success(request, '高峰时段配置已更新')
            return redirect('courier:peak_hour_list')
    else:
        form = StationPeakHourForm(instance=ph)
    return render(request, 'courier/peak_hour_form.html', {'form': form, 'title': '编辑高峰时段'})


def peak_hour_delete(request, pk):
    ph = get_object_or_404(StationPeakHour, pk=pk)
    if request.method == 'POST':
        ph.delete()
        messages.success(request, '高峰时段配置已删除')
        return redirect('courier:peak_hour_list')
    return render(request, 'courier/peak_hour_confirm_delete.html', {'peak_hour': ph})


def api_simulation_result(request, pk):
    sim = get_object_or_404(SimulationRun, pk=pk)
    if sim.status != 'completed':
        return JsonResponse({'error': '仿真尚未完成运行'}, status=400)
    result_data = get_simulation_result_data(pk)
    return JsonResponse({
        'simulation': {
            'id': sim.pk,
            'name': sim.name,
            'total_tasks': sim.total_tasks_simulated,
            'avg_wait': sim.avg_wait_time,
            'max_wait': sim.max_wait_time,
            'avg_total': sim.avg_total_time,
            'delay_count': sim.total_delay_count,
        },
        'task_wait_list': result_data['task_wait_list'],
        'heatmap': result_data['heatmap_data'],
        'time_labels': result_data['time_labels'],
        'station_codes': result_data['station_codes'],
        'bottlenecks': result_data['bottleneck_list'],
        'priority_analysis': result_data['priority_analysis'],
        'time_fluctuation': result_data['time_fluctuation'],
    })
