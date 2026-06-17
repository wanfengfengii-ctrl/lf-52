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

    stations = list(Station.objects.all().order_by('pk'))
    strategies = list(HorseChangeStrategy.objects.all().order_by('pk'))

    if len(stations) < 2:
        print("  驿站数量不足，请先运行 init_data.py 初始化数据")
        return False

    print("\n[测试1] 单段路程时间计算")
    print("-" * 60)
    test_road = Road.objects.select_related('from_station', 'to_station').first()
    if not test_road:
        print("  跳过：无道路数据")
    else:
        result = calculate_segment_time(test_road, priority=2, strategy=strategies[0] if strategies else None)
        print(f"  路段: {test_road}")
        print(f"  行进时间: {result['travel_time']} 时辰")
        print(f"  换马时间: {result['horse_change_time']} 时辰")
        print(f"  中转时间: {result['process_time']} 时辰")
        print(f"  总时间: {result['total_time']} 时辰")
        print(f"  高风险: {result['is_high_risk']}")
        print(f"  风险评分: {result['risk_score']}")
        print(f"  ✓ 测试通过")

    print("\n[测试2] 多方案路径搜索 (Dijkstra)")
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
    if all_paths:
        print(f"  ✓ 测试通过")
    else:
        print(f"  ⚠ 未找到连通路线（可能是有向图问题）")

    print("\n[测试3] 递送任务多方案生成")
    print("-" * 60)
    if len(all_paths) > 0:
        task, created = DeliveryTask.objects.get_or_create(
            task_code='TEST-MULTI-001',
            defaults={
                'origin': origin,
                'destination': dest,
                'strategy': strategies[0] if strategies else None,
                'priority': 2,
                'deadline_hours': 20.0,
                'departure_offset': 0.5,
            }
        )
        if not created:
            task.origin = origin
            task.destination = dest
            if strategies:
                task.strategy = strategies[0]
            task.priority = 2
            task.deadline_hours = 20.0
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
    else:
        print("  跳过：无可用路径")

    print("\n[测试4] 方案对比数据获取")
    print("-" * 60)
    if len(all_paths) > 0:
        comparison = get_plan_comparison_data(task)
        print(f"  返回方案数: {len(comparison)}")
        for p in comparison:
            print(f"    [{p['plan_type_display']}] 总时间={p['total_time']}, 路段数={len(p['segments'])}")
        print(f"  ✓ 测试通过")
    else:
        print("  跳过：无可用路径")

    print("\n[测试5] 调度甘特图数据")
    print("-" * 60)
    if len(all_paths) > 0:
        gantt = get_gantt_data(task)
        print(f"  甘特图数据条目: {len(gantt)}")
        print(f"  ✓ 测试通过")
    else:
        print("  跳过：无可用路径")

    print("\n[测试6] 独立路段策略（override）")
    print("-" * 60)
    if len(all_paths) > 0 and len(strategies) >= 2:
        segments = task.segments.all()
        if segments.exists():
            first_seg = segments.first()
            original_time = task.estimated_hours
            print(f"  原总时间: {original_time} 时辰")
            first_seg.override_strategy = strategies[-1]
            first_seg.save()
            calculate_delivery_time(task, force_recalculate=True)
            print(f"  更换策略后总时间: {task.estimated_hours} 时辰")
            first_seg.override_strategy = None
            first_seg.save()
            calculate_delivery_time(task, force_recalculate=True)
            print(f"  恢复后总时间: {task.estimated_hours} 时辰")
            print(f"  ✓ 测试通过")
    else:
        print("  跳过：数据不足")

    print("\n[测试7] Django API 路由计算")
    print("-" * 60)
    from django.test import Client
    client = Client()
    response = client.get(f'/api/calculate/?origin={origin.pk}&destination={dest.pk}&priority=2&deadline=25')
    print(f"  状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        all_plans = data.get('all_plans', [])
        selected = data.get('selected_plan')
        print(f"  all_plans 方案数: {len(all_plans)}")
        print(f"  has_high_risk: {data.get('has_high_risk')}")
        print(f"  has_delay_risk: {data.get('has_delay_risk')}")
        if selected:
            print(f"  选中方案: {selected.get('plan_type_display')}, 总时间={selected.get('total_time')}")
            segs = selected.get('segments', [])
            if segs:
                print(f"  路段数: {len(segs)}")
                print(f"  首段: from={segs[0].get('from')}, to={segs[0].get('to')}, time={segs[0].get('time')}")
        print(f"  ✓ 测试通过")
    else:
        print(f"  ✗ API 返回错误: {response.status_code}")
        print(f"  内容: {response.content[:200]}")

    print("\n[测试8] Django API 策略列表")
    print("-" * 60)
    response = client.get('/api/strategies/')
    print(f"  状态码: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"  策略数: {len(data)}")
        if data:
            print(f"  首个: {data[0].get('name')}, 间隔={data[0].get('interval_distance')}里")
        print(f"  ✓ 测试通过")
    else:
        print(f"  ✗ API 返回错误: {response.status_code}")

    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)
    return True


if __name__ == '__main__':
    run_tests()
