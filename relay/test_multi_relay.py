import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'relay.settings')
django.setup()

from courier.models import Station, Road, HorseChangeStrategy, WeatherRecord, DeliveryTask, DeliveryPlan
from courier.engine import (
    calculate_segment_time, find_all_paths, generate_all_plans,
    calculate_delivery_time, get_plan_comparison_data, get_gantt_data
)


def run_tests():
    print("=" * 60)
    print("多驿站接力调度优化 - 功能测试")
    print("=" * 60)

    if Station.objects.count() == 0:
        print("\n[初始化] 正在创建初始测试数据...")
        stations_data = [
            ('YZ001', '长安驿', 34.26, 108.94, '京畿首驿，西出第一站'),
            ('YZ002', '灞桥驿', 34.37, 109.07, '灞桥折柳处'),
            ('YZ003', '渭南驿', 34.50, 109.50, '渭水之南'),
            ('YZ004', '华阴驿', 34.57, 110.09, '华山脚下'),
            ('YZ005', '潼关驿', 34.54, 110.24, '潼关天险'),
            ('YZ006', '函谷驿', 34.64, 110.54, '函谷关前'),
            ('YZ007', '陕州驿', 34.77, 111.20, '陕州古城'),
            ('YZ008', '洛阳驿', 34.68, 112.45, '东都洛阳'),
        ]
        for code, name, lat, lng, desc in stations_data:
            Station.objects.create(code=code, name=name, latitude=lat, longitude=lng, description=desc)
        print(f"  ✓ 创建 {len(stations_data)} 个驿站")

        stations = list(Station.objects.all().order_by('code'))
        roads_data = [
            (0, 1, 30, 2, 1),
            (1, 2, 50, 5, 2),
            (2, 3, 60, 8, 2),
            (3, 4, 40, 12, 3),
            (4, 5, 35, 15, 4),
            (5, 6, 70, 3, 2),
            (6, 7, 100, 5, 1),
        ]
        for from_idx, to_idx, dist, slope, grade in roads_data:
            Road.objects.create(
                from_station=stations[from_idx],
                to_station=stations[to_idx],
                distance=dist,
                slope=slope,
                grade=grade,
            )
        print(f"  ✓ 创建 {len(roads_data)} 条道路")

        strategies_data = [
            ('快速换马', 30, 0.3, '每30里换马，适合加急文书'),
            ('标准换马', 50, 0.5, '每50里换马，常规递送'),
            ('长途缓行', 80, 0.8, '每80里换马，节省换马时间'),
        ]
        for name, interval, change_time, desc in strategies_data:
            HorseChangeStrategy.objects.create(name=name, interval_distance=interval, change_time=change_time, description=desc)
        print(f"  ✓ 创建 {len(strategies_data)} 种换马策略")

        for road in Road.objects.all():
            WeatherRecord.objects.create(road=road, weather_type=1)
        print(f"  ✓ 创建天气记录")

    stations = list(Station.objects.all().order_by('code'))
    strategies = list(HorseChangeStrategy.objects.all())

    print("\n" + "=" * 60)
    print("[测试1] 单段路程时间计算")
    print("-" * 60)
    test_road = Road.objects.select_related('from_station', 'to_station').first()
    result = calculate_segment_time(test_road, priority=2, strategy=strategies[0])
    print(f"  路段: {test_road}")
    print(f"  行进时间: {result['travel_time']} 时辰")
    print(f"  换马时间: {result['horse_change_time']} 时辰")
    print(f"  中转时间: {result['process_time']} 时辰")
    print(f"  总时间: {result['total_time']} 时辰")
    print(f"  高风险: {result['is_high_risk']}")
    print(f"  风险评分: {result['risk_score']}")
    print(f"  ✓ 测试通过")

    print("\n" + "=" * 60)
    print("[测试2] 多方案路径搜索 (Dijkstra)")
    print("-" * 60)
    origin = stations[0]
    dest = stations[-1]
    all_paths = find_all_paths(origin.pk, dest.pk, priority=1)
    print(f"  路线: {origin.code} → {dest.code}")
    print(f"  找到方案数: {len(all_paths)}")
    for plan_type, roads, results in all_paths:
        total_time = sum(r['total_time'] for r in results)
        total_dist = sum(r['distance'] for r in results)
        risk_count = sum(1 for r in results if r['is_high_risk'])
        print(f"    [{plan_type}] 总时间={total_time:.2f}时辰, 距离={total_dist:.1f}里, 风险段={risk_count}")
    print(f"  ✓ 测试通过")

    print("\n" + "=" * 60)
    print("[测试3] 递送任务多方案生成")
    print("-" * 60)
    task, created = DeliveryTask.objects.get_or_create(
        task_code='TEST-001',
        defaults={
            'origin': origin,
            'destination': dest,
            'strategy': strategies[1],
            'priority': 2,
            'deadline_hours': 10.0,
            'departure_offset': 0.5,
        }
    )
    if not created:
        task.origin = origin
        task.destination = dest
        task.strategy = strategies[1]
        task.priority = 2
        task.deadline_hours = 10.0
        task.departure_offset = 0.5
        task.save()

    calculate_delivery_time(task, force_recalculate=True)
    print(f"  任务编号: {task.task_code}")
    print(f"  预计送达: {task.estimated_hours} 时辰")
    print(f"  延误预警: {task.delay_warning}")
    print(f"  高风险: {task.has_high_risk}")
    plans = DeliveryPlan.objects.filter(task=task)
    print(f"  生成方案数: {plans.count()}")
    for plan in plans:
        print(f"    [{plan.get_plan_type_display()}] 总时间={plan.total_time}时辰, "
              f"距离={plan.total_distance}里, 延误概率={plan.delay_probability*100:.0f}%, "
              f"风险段={plan.risk_count}, 延误风险={'是' if plan.is_delay_risk else '否'}")
    print(f"  ✓ 测试通过")

    print("\n" + "=" * 60)
    print("[测试4] 方案对比数据获取")
    print("-" * 60)
    comparison = get_plan_comparison_data(task)
    print(f"  返回方案数: {len(comparison)}")
    for p in comparison:
        print(f"    [{p['plan_type_display']}] 总时间={p['total_time']}, 路段数={len(p['segments'])}")
    print(f"  ✓ 测试通过")

    print("\n" + "=" * 60)
    print("[测试5] 调度甘特图数据")
    print("-" * 60)
    gantt = get_gantt_data(task)
    print(f"  甘特图数据条目: {len(gantt)}")
    print(f"  ✓ 测试通过")

    print("\n" + "=" * 60)
    print("[测试6] 独立路段策略（override）")
    print("-" * 60)
    segments = task.segments.all()
    if segments.exists():
        first_seg = segments.first()
        print(f"  原本段用时: {first_seg.segment_time} 时辰")
        first_seg.override_strategy = strategies[0]
        first_seg.save()
        calculate_delivery_time(task, force_recalculate=True)
        print(f"  更换快速策略后总时间: {task.estimated_hours} 时辰")
        first_seg.override_strategy = None
        first_seg.save()
        print(f"  ✓ 测试通过")
    else:
        print(f"  - 跳过：没有路段数据")

    print("\n" + "=" * 60)
    print("[测试7] API 路由计算")
    print("-" * 60)
    from django.test import Client
    client = Client()
    response = client.get(f'/api/calculate/?origin={origin.pk}&destination={dest.pk}&priority=2&deadline=12')
    print(f"  状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  方案数: {len(data.get('all_plans', []))}")
        print(f"  存在高风险: {data.get('has_high_risk')}")
        print(f"  存在延误风险: {data.get('has_delay_risk')}")
        selected = data.get('selected_plan', {})
        if selected:
            print(f"  选中方案: {selected.get('plan_type_display')}, 总时间={selected.get('total_time')}")
        print(f"  ✓ 测试通过")
    else:
        print(f"  ✗ API 返回错误: {response.status_code}")

    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)


if __name__ == '__main__':
    run_tests()
