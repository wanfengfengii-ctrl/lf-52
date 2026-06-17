import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'relay.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from courier.models import Station, Road, HorseChangeStrategy, DeliveryTask
from courier.core.datatypes import RoadInfo, StrategyInfo, StationInfo
from courier.engines.segment_engine import SegmentEngine, calculate_segment_time
from courier.engines.route_engine import RouteEngine, find_path, find_all_paths
from courier.engines.plan_engine import PlanEngine, generate_all_plans
from courier.services.delivery_service import DeliveryService
from courier.core.result import Result


def test_data_classes():
    print("=== 测试数据类 ===")
    road = RoadInfo(
        id=1, from_station_id=1, to_station_id=2,
        from_station_code='A01', to_station_code='A02',
        distance=50.0, slope=5.0, grade=2
    )
    print(f"RoadInfo: {road}")
    assert road.id == 1
    assert road.distance == 50.0
    print("✓ 数据类创建成功\n")


def test_segment_engine():
    print("=== 测试路段时间计算引擎 ===")
    engine = SegmentEngine()
    road = RoadInfo(
        id=1, from_station_id=1, to_station_id=2,
        distance=60.0, slope=0.0, grade=2
    )

    result = engine.calculate(road, priority=1)
    print(f"基础速度下：{result.total_time} 时辰, 速度: {result.speed} 里/时辰")
    assert result.total_time > 0
    assert result.speed > 0

    result_fast = engine.calculate(road, priority=3)
    print(f"最高优先级下：{result_fast.total_time} 时辰")
    assert result_fast.total_time < result.total_time

    result_rain = engine.calculate(road, weather_type=4, priority=1)
    print(f"大雨天气下：{result_rain.total_time} 时辰, 高风险: {result_rain.is_high_risk}")
    assert result_rain.total_time > result.total_time

    strategy = StrategyInfo(id=1, name='快马策略', interval_distance=30, change_time=0.3)
    result_strat = engine.calculate(road, priority=1, strategy=strategy)
    print(f"换马策略下：{result_strat.total_time} 时辰 (换马时间: {result_strat.horse_change_time})")
    assert result_strat.horse_change_time > 0

    print("✓ 路段时间计算引擎测试通过\n")


def test_route_engine():
    print("=== 测试路线计算引擎 ===")
    roads = [
        RoadInfo(id=1, from_station_id=1, to_station_id=2, from_station_code='A01', to_station_code='A02', distance=30.0, grade=2),
        RoadInfo(id=2, from_station_id=2, to_station_id=3, from_station_code='A02', to_station_code='A03', distance=40.0, grade=2),
        RoadInfo(id=3, from_station_id=1, to_station_id=3, from_station_code='A01', to_station_code='A03', distance=80.0, grade=3),
    ]

    engine = RouteEngine()
    graph = engine.build_graph(roads)
    print(f"构建图完成，节点数: {len(graph)}")
    assert 1 in graph
    assert 2 in graph
    print(f"  节点 1 的出边: {len(graph[1])} 条")
    print(f"  节点 2 的出边: {len(graph.get(2, []))} 条")

    path_result = engine.find_path(roads, 1, 3, optimize='time')
    print(f"最短路径: {len(path_result.path_roads)} 段, 总时间: {path_result.total_time} 时辰")
    assert path_result is not None
    assert path_result.station_count == 2

    all_paths = engine.find_all_paths(roads, 1, 3)
    print(f"所有方案数: {len(all_paths)}")
    for ptype, presult in all_paths:
        print(f"  - {ptype}: {presult.total_time} 时辰, {presult.risk_count} 个高风险段")
    assert len(all_paths) >= 2

    print("✓ 路线计算引擎测试通过\n")


def test_plan_engine():
    print("=== 测试方案生成引擎 ===")
    roads = [
        RoadInfo(id=1, from_station_id=1, to_station_id=2, from_station_code='A01', to_station_code='A02', distance=30.0, grade=2),
        RoadInfo(id=2, from_station_id=2, to_station_id=3, from_station_code='A02', to_station_code='A03', distance=40.0, grade=2),
        RoadInfo(id=3, from_station_id=1, to_station_id=3, from_station_code='A01', to_station_code='A03', distance=100.0, grade=5),
    ]

    engine = PlanEngine()
    result = engine.generate_all_plans(
        roads=roads,
        origin_id=1,
        destination_id=3,
        priority=2,
        deadline_hours=3.0,
    )

    print(f"生成方案结果: success={result.success}")
    if result.success:
        print(f"方案数: {len(result.data)}")
        for plan in result.data:
            print(f"  - {plan.plan_type_display}: {plan.total_time} 时辰, 延误风险: {plan.is_delay_risk} ({plan.delay_probability})")
            print(f"    路段数: {len(plan.segments)}")
            for seg in plan.segments:
                print(f"      {seg.order}. {seg.from_station_code}→{seg.to_station_code}: {seg.segment_time} 时辰")

        comparison = engine.get_plan_comparison_data(result.data)
        print(f"\n方案对比数据: {len(comparison)} 条")

        gantt = engine.get_gantt_data(result.data)
        print(f"甘特图数据: {len(gantt)} 条")

    print("✓ 方案生成引擎测试通过\n")


def test_result_wrapper():
    print("=== 测试结果包装类 ===")
    success = Result.ok({'value': 42}, meta='test')
    print(f"成功结果: success={success.success}, data={success.data}")
    assert success.is_success
    assert success.unwrap()['value'] == 42

    failure = Result.fail('出错了', error_code='TEST_ERROR')
    print(f"失败结果: success={failure.success}, error={failure.error}, code={failure.error_code}")
    assert failure.is_failure
    assert failure.error_code == 'TEST_ERROR'

    try:
        failure.unwrap()
        assert False, "应该抛出异常"
    except Exception as e:
        print(f"unwrap 失败时正确抛出异常: {e}")

    result_dict = success.to_dict()
    print(f"to_dict: {result_dict}")
    assert result_dict['success'] is True

    print("✓ 结果包装类测试通过\n")


def test_with_database():
    print("=== 测试与数据库集成 ===")
    stations = Station.objects.all()
    roads = Road.objects.all()

    if not stations.exists() or not roads.exists():
        print("⚠ 数据库中没有数据，跳过数据库集成测试")
        return

    print(f"驿站数: {stations.count()}, 道路数: {roads.count()}")

    service = DeliveryService()

    origin = stations.first()
    destination = stations.last()
    print(f"测试路线: {origin.code} → {destination.code}")

    result = service.calculate_route(
        origin_id=origin.pk,
        destination_id=destination.pk,
        priority=2,
    )

    print(f"路线计算结果: success={result.success}")
    if result.success:
        data = result.data
        print(f"  方案数: {len(data['all_plans'])}")
        print(f"  选中方案: {data['selected_plan']['plan_type']} - {data['selected_plan']['total_time']} 时辰")
        print(f"  有高风险: {data['has_high_risk']}")
        print(f"  有延误风险: {data['has_delay_risk']}")

    tasks = DeliveryTask.objects.all()
    if tasks.exists():
        task = tasks.first()
        print(f"\n测试任务: {task.task_code}")

        est_time = service.calculate_delivery_time(task, force_recalculate=True)
        print(f"  预计送达: {est_time} 时辰")

        analysis = service.get_task_analysis_data(task)
        print(f"  分析数据标签数: {len(analysis['labels'])}")

        plans = service.get_plan_comparison_for_task(task)
        print(f"  方案数: {len(plans)}")

        gantt = service.get_gantt_for_task(task)
        print(f"  甘特图项数: {len(gantt)}")

    print("✓ 数据库集成测试通过\n")


def main():
    print("=" * 60)
    print("驿递系统架构重构 - 新引擎验证测试")
    print("=" * 60 + "\n")

    try:
        test_data_classes()
        test_segment_engine()
        test_route_engine()
        test_plan_engine()
        test_result_wrapper()
        test_with_database()

        print("=" * 60)
        print("✓ 所有测试通过！新架构运行正常")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
