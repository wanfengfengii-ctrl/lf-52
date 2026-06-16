import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q
from .models import Station, Road, HorseChangeStrategy, WeatherRecord, DeliveryTask, DeliverySegment
from .forms import (
    StationForm, RoadForm, HorseChangeStrategyForm,
    WeatherRecordForm, DeliveryTaskForm, DeliveryTaskStatusForm,
)
from .engine import (
    calculate_delivery_time, recalculate_affected_tasks,
    get_analysis_data, find_path, calculate_segment_time,
)


def index(request):
    station_count = Station.objects.count()
    road_count = Road.objects.count()
    task_count = DeliveryTask.objects.count()
    strategy_count = HorseChangeStrategy.objects.count()
    return render(request, 'courier/index.html', {
        'station_count': station_count,
        'road_count': road_count,
        'task_count': task_count,
        'strategy_count': strategy_count,
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
            messages.success(request, f'递送任务创建成功，预计送达时间：{task.estimated_hours}时辰')
            return redirect('courier:task_detail', pk=task.pk)
    else:
        form = DeliveryTaskForm()
    return render(request, 'courier/task_form.html', {'form': form, 'title': '新建递送任务'})


def task_detail(request, pk):
    task = get_object_or_404(DeliveryTask, pk=pk)
    segments = task.segments.select_related('road', 'road__from_station', 'road__to_station').all()

    segment_details = []
    for seg in segments:
        road = seg.road
        result = calculate_segment_time(road=road, priority=task.priority, strategy=task.strategy)
        segment_details.append({
            'segment': seg,
            'detail': result,
        })

    chart_data = get_analysis_data(task)

    context = {
        'task': task,
        'segments': segments,
        'segment_details': segment_details,
        'chart_data': json.dumps(chart_data, ensure_ascii=False),
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
    messages.success(request, f'已重新计算，预计送达时间：{task.estimated_hours}时辰')
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
            task_data.append({
                'task': task,
                'chart_data': json.dumps(chart, ensure_ascii=False),
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

    context = {
        'task_data': task_data,
        'comparison_data': json.dumps(comparison_data, ensure_ascii=False),
        'comparison_available': len(comparison_data) >= 2,
    }
    return render(request, 'courier/analysis.html', context)


def api_stations(request):
    stations = Station.objects.all()
    data = [
        {'id': s.pk, 'code': s.code, 'name': s.name, 'lat': s.latitude, 'lng': s.longitude}
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

    if not origin_id or not dest_id:
        return JsonResponse({'error': '需要指定起点和终点'}, status=400)

    path = find_path(int(origin_id), int(dest_id))
    if not path:
        return JsonResponse({'error': '没有连通路线'}, status=404)

    strategy = None
    if strategy_id:
        strategy = HorseChangeStrategy.objects.filter(pk=int(strategy_id)).first()

    total_time = 0
    segments = []
    for idx, road in enumerate(path):
        result = calculate_segment_time(road=road, priority=priority, strategy=strategy)
        total_time += result['total_time']
        segments.append({
            'order': idx + 1,
            'from': road.from_station.code,
            'to': road.to_station.code,
            'distance': road.distance,
            'time': result['total_time'],
            'travel_time': result['travel_time'],
            'horse_change_time': result['horse_change_time'],
            'is_high_risk': result['is_high_risk'],
        })

    return JsonResponse({
        'total_time': round(total_time, 2),
        'segments': segments,
        'has_high_risk': any(s['is_high_risk'] for s in segments),
    })
