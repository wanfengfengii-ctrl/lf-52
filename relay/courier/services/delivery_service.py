from typing import List, Optional, Dict, Any

from django.db import transaction
from django.db.models import Q

from ..models import (
    Station, Road, HorseChangeStrategy, WeatherRecord,
    DeliveryTask, DeliverySegment, DeliveryPlan, PlanSegment,
)
from ..core.datatypes import (
    RoadInfo, StrategyInfo, StationInfo,
    PlanInfo, PlanSegmentInfo,
)
from ..core.result import Result
from ..engines import PlanEngine, SegmentEngine
from ..engines.segment_engine import WEATHER_SEVERITY_MAP, WEATHER_DISPLAY_MAP


class DeliveryService:
    """递送任务服务 - 业务流程编排层"""

    def __init__(self, plan_engine: PlanEngine = None):
        self.plan_engine = plan_engine or PlanEngine()
        self.segment_engine = self.plan_engine.segment_engine

    def _load_roads(self) -> List[RoadInfo]:
        """加载所有道路信息"""
        roads = Road.objects.select_related('from_station', 'to_station').all()
        return [RoadInfo.from_model(r) for r in roads]

    def _load_strategy(self, strategy_id: Optional[int]) -> Optional[StrategyInfo]:
        """加载换马策略"""
        if not strategy_id:
            return None
        try:
            strategy = HorseChangeStrategy.objects.get(pk=strategy_id)
            return StrategyInfo.from_model(strategy)
        except HorseChangeStrategy.DoesNotExist:
            return None

    def _load_station_process_times(self) -> Dict[int, float]:
        """加载所有驿站处理时间"""
        stations = Station.objects.all()
        return {s.pk: s.process_time or 0.0 for s in stations}

    def _get_latest_weather_for_road(self, road_id: int) -> Optional[int]:
        """获取道路的最新天气类型"""
        latest = WeatherRecord.objects.filter(road_id=road_id).first()
        return latest.weather_type if latest else None

    def calculate_route(
        self,
        origin_id: int,
        destination_id: int,
        strategy_id: Optional[int] = None,
        priority: int = 1,
        deadline: Optional[float] = None,
        plan_type: str = 'fastest',
    ) -> Result[Dict[str, Any]]:
        """
        计算路线（API用）

        Args:
            origin_id: 起点驿站ID
            destination_id: 终点驿站ID
            strategy_id: 策略ID
            priority: 优先级
            deadline: 要求时限
            plan_type: 选用方案类型

        Returns:
            Result 包含选中方案、所有方案、风险信息等
        """
        roads = self._load_roads()
        strategy = self._load_strategy(strategy_id)

        result = self.plan_engine.generate_all_plans(
            roads=roads,
            origin_id=origin_id,
            destination_id=destination_id,
            priority=priority,
            strategy=strategy,
            deadline_hours=deadline,
        )

        if result.is_failure:
            return result

        plans = result.data
        plans_output = []
        for plan in plans:
            segments_output = []
            for idx, seg in enumerate(plan.segments):
                segments_output.append({
                    'order': idx + 1,
                    'from': seg.from_station_code,
                    'to': seg.to_station_code,
                    'distance': seg.distance,
                    'time': seg.segment_time,
                    'travel_time': seg.travel_time,
                    'horse_change_time': seg.horse_change_time,
                    'process_time': seg.process_time,
                    'is_high_risk': seg.is_high_risk,
                    'grade': seg.distance and 0,  # 兼容字段
                    'slope': 0,
                })

            plans_output.append({
                'plan_type': plan.plan_type,
                'plan_type_display': plan.plan_type_display,
                'total_time': plan.total_time,
                'total_distance': plan.total_distance,
                'risk_count': plan.risk_count,
                'station_count': plan.station_count,
                'is_delay_risk': plan.is_delay_risk,
                'delay_probability': plan.delay_probability,
                'segments': segments_output,
            })

        selected = next((p for p in plans_output if p['plan_type'] == plan_type),
                        plans_output[0] if plans_output else None)

        return Result.ok({
            'selected_plan': selected,
            'all_plans': plans_output,
            'has_high_risk': any(p['risk_count'] > 0 for p in plans_output),
            'has_delay_risk': any(p['is_delay_risk'] for p in plans_output),
        })

    @transaction.atomic
    def generate_all_plans_for_task(self, task: DeliveryTask, force_recalculate: bool = False) -> List[DeliveryPlan]:
        """
        为任务生成所有方案并保存

        Args:
            task: 递送任务
            force_recalculate: 是否强制重算

        Returns:
            方案列表
        """
        if not force_recalculate and task.plans.exists():
            return list(task.plans.select_related().all())

        task.plans.all().delete()

        roads = self._load_roads()
        strategy = self._load_strategy(task.strategy_id)

        result = self.plan_engine.generate_all_plans(
            roads=roads,
            origin_id=task.origin_id,
            destination_id=task.destination_id,
            priority=task.priority,
            strategy=strategy,
            departure_offset=task.departure_offset or 0.0,
            deadline_hours=task.deadline_hours,
        )

        if result.is_failure:
            return []

        plan_infos = result.data
        plans = []

        for plan_info in plan_infos:
            plan = DeliveryPlan.objects.create(
                task=task,
                plan_type=plan_info.plan_type,
                total_time=plan_info.total_time,
                total_distance=plan_info.total_distance,
                risk_count=plan_info.risk_count,
                station_count=plan_info.station_count,
                is_delay_risk=plan_info.is_delay_risk,
                delay_probability=plan_info.delay_probability,
            )

            plan_segments = []
            for seg_info in plan_info.segments:
                plan_segments.append(PlanSegment(
                    plan=plan,
                    road_id=seg_info.road_id,
                    order=seg_info.order,
                    segment_time=seg_info.segment_time,
                    travel_time=seg_info.travel_time,
                    horse_change_time=seg_info.horse_change_time,
                    process_time=seg_info.process_time,
                    is_high_risk=seg_info.is_high_risk,
                    departure_time=seg_info.departure_time,
                    arrival_time=seg_info.arrival_time,
                    strategy_name=seg_info.strategy_name,
                    weather_display=seg_info.weather_display,
                ))
            PlanSegment.objects.bulk_create(plan_segments)

            plans.append(plan)

        return plans

    @transaction.atomic
    def calculate_delivery_time(self, task: DeliveryTask, force_recalculate: bool = False) -> Optional[float]:
        """
        计算任务送达时间

        Args:
            task: 递送任务
            force_recalculate: 是否强制重算

        Returns:
            预计送达时间（时辰）
        """
        plans = self.generate_all_plans_for_task(task, force_recalculate=force_recalculate)
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
        first_seg = True
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
            if first_seg:
                seg.departure_time = task.departure_offset
                seg.save()
                first_seg = False

        task.estimated_hours = selected_plan.total_time
        task.has_high_risk = selected_plan.risk_count > 0
        task.delay_warning = selected_plan.is_delay_risk
        task.save()

        return task.estimated_hours

    def recalculate_affected_tasks(self, road_id: int) -> int:
        """
        重新计算受某条道路影响的所有任务

        Args:
            road_id: 道路ID

        Returns:
            重算的任务数
        """
        from ..models import PlanSegment

        affected_segments = DeliverySegment.objects.filter(road_id=road_id).select_related('task')
        affected_plan_segments = PlanSegment.objects.filter(road_id=road_id).select_related('plan__task')
        task_ids = set(seg.task_id for seg in affected_segments)
        for ps in affected_plan_segments:
            task_ids.add(ps.plan.task_id)

        count = 0
        for task_id in task_ids:
            try:
                task = DeliveryTask.objects.get(pk=task_id)
                self.calculate_delivery_time(task, force_recalculate=True)
                count += 1
            except DeliveryTask.DoesNotExist:
                pass
        return count

    def get_task_analysis_data(self, task: DeliveryTask) -> Dict[str, Any]:
        """
        获取任务分析图表数据

        Args:
            task: 递送任务

        Returns:
            图表数据字典
        """
        segments = task.segments.select_related('road', 'road__from_station', 'road__to_station').all()
        if not segments:
            self.calculate_delivery_time(task, force_recalculate=True)
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

        strategy = self._load_strategy(task.strategy_id)

        for seg in segments:
            road_info = RoadInfo.from_model(seg.road)
            weather_type = seg.override_weather
            if not weather_type:
                weather_type = self._get_latest_weather_for_road(seg.road_id)

            seg_strategy = strategy
            if seg.override_strategy_id:
                seg_strategy = self._load_strategy(seg.override_strategy_id)

            result = self.segment_engine.calculate(
                road=road_info,
                weather_type=weather_type,
                priority=task.priority,
                strategy=seg_strategy,
                process_time=seg.road.to_station.process_time if seg.road.to_station else 0,
            )

            chart_data['labels'].append(f'{seg.road.from_station.code}→{seg.road.to_station.code}')
            chart_data['travel_times'].append(result.travel_time)
            chart_data['horse_change_times'].append(result.horse_change_time)
            chart_data['process_times'].append(result.process_time)
            chart_data['total_times'].append(result.total_time)
            chart_data['risks'].append(1 if result.is_high_risk else 0)
            chart_data['distances'].append(result.distance)
            chart_data['speeds'].append(result.speed)
            chart_data['departures'].append(seg.departure_time or 0)
            chart_data['arrivals'].append(seg.arrival_time or 0)

        return chart_data

    def get_plan_comparison_for_task(self, task: DeliveryTask) -> List[Dict[str, Any]]:
        """
        获取任务的方案对比数据

        Args:
            task: 递送任务

        Returns:
            方案对比数据列表
        """
        plans = task.plans.select_related().all()
        if not plans:
            self.generate_all_plans_for_task(task, force_recalculate=True)
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

    def get_gantt_for_task(self, task: DeliveryTask) -> List[Dict[str, Any]]:
        """
        获取任务的甘特图数据

        Args:
            task: 递送任务

        Returns:
            甘特图数据列表
        """
        plans = task.plans.select_related().all()
        if not plans:
            self.generate_all_plans_for_task(task, force_recalculate=True)
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


_default_delivery_service = DeliveryService()


def calculate_delivery_time(task: DeliveryTask, force_recalculate: bool = False) -> Optional[float]:
    """便捷函数 - 计算任务送达时间"""
    return _default_delivery_service.calculate_delivery_time(task, force_recalculate=force_recalculate)


def recalculate_affected_tasks(road_id: int) -> int:
    """便捷函数 - 重算受影响任务"""
    return _default_delivery_service.recalculate_affected_tasks(road_id)


def generate_all_plans_for_task(task: DeliveryTask, force_recalculate: bool = False) -> List[DeliveryPlan]:
    """便捷函数 - 为任务生成所有方案"""
    return _default_delivery_service.generate_all_plans_for_task(task, force_recalculate=force_recalculate)


def get_task_analysis_data(task: DeliveryTask) -> Dict[str, Any]:
    """便捷函数 - 获取任务分析数据"""
    return _default_delivery_service.get_task_analysis_data(task)


def get_plan_comparison_for_task(task: DeliveryTask) -> List[Dict[str, Any]]:
    """便捷函数 - 获取方案对比数据"""
    return _default_delivery_service.get_plan_comparison_for_task(task)


def get_gantt_for_task(task: DeliveryTask) -> List[Dict[str, Any]]:
    """便捷函数 - 获取甘特图数据"""
    return _default_delivery_service.get_gantt_for_task(task)


def calculate_route_api(
    origin_id: int,
    destination_id: int,
    strategy_id: Optional[int] = None,
    priority: int = 1,
    deadline: Optional[float] = None,
    plan_type: str = 'fastest',
) -> Result[Dict[str, Any]]:
    """便捷函数 - 计算路线（API用）"""
    return _default_delivery_service.calculate_route(
        origin_id=origin_id,
        destination_id=destination_id,
        strategy_id=strategy_id,
        priority=priority,
        deadline=deadline,
        plan_type=plan_type,
    )
