from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from ..core.datatypes import (
    RoadInfo, StrategyInfo, SegmentResult,
    PlanInfo, PlanSegmentInfo, PathResult,
)
from ..core.result import Result
from .route_engine import RouteEngine
from .segment_engine import SegmentEngine


DELAY_RISK_THRESHOLD = 0.3

PLAN_TYPE_DISPLAY = {
    'fastest': '最短送达方案',
    'safest': '最稳妥方案',
    'balanced': '均衡方案',
    'alternative': '备选方案',
}


class PlanEngine:
    """方案生成引擎 - 生成多方案递送计划"""

    def __init__(
        self,
        route_engine: RouteEngine = None,
        segment_engine: SegmentEngine = None,
        delay_risk_threshold: float = DELAY_RISK_THRESHOLD,
    ):
        self.route_engine = route_engine or RouteEngine(segment_engine=segment_engine)
        self.segment_engine = self.route_engine.segment_engine
        self.delay_risk_threshold = delay_risk_threshold

    def compute_delay_probability(
        self,
        total_time: float,
        deadline_hours: Optional[float],
        risk_count: int,
        station_count: int,
    ) -> float:
        """
        计算延误概率

        Args:
            total_time: 总耗时
            deadline_hours: 要求时限
            risk_count: 高风险段数
            station_count: 途经驿站数

        Returns:
            延误概率 (0.0 - 1.0)
        """
        if deadline_hours is None or deadline_hours <= 0:
            return 0.0
        ratio = total_time / deadline_hours
        base_prob = max(0.0, (ratio - 0.7) / 0.5)
        risk_factor = min(1.0, risk_count * 0.15 + station_count * 0.02)
        prob = min(1.0, base_prob * 0.6 + risk_factor * 0.4)
        return round(prob, 2)

    def generate_plan_from_path(
        self,
        plan_type: str,
        path_result: PathResult,
        departure_offset: float = 0.0,
        deadline_hours: Optional[float] = None,
    ) -> PlanInfo:
        """
        从路径结果生成方案信息

        Args:
            plan_type: 方案类型
            path_result: 路径计算结果
            departure_offset: 出发时间偏移
            deadline_hours: 要求时限

        Returns:
            PlanInfo 方案信息
        """
        segments = []
        current_time = departure_offset

        for idx, (road, seg_result) in enumerate(zip(path_result.path_roads, path_result.path_results)):
            departure = current_time
            arrival = current_time + seg_result.total_time

            seg_info = PlanSegmentInfo(
                order=idx + 1,
                road_id=road.id,
                from_station_code=road.from_station_code,
                to_station_code=road.to_station_code,
                distance=seg_result.distance,
                segment_time=seg_result.total_time,
                travel_time=seg_result.travel_time,
                horse_change_time=seg_result.horse_change_time,
                process_time=seg_result.process_time,
                is_high_risk=seg_result.is_high_risk,
                departure_time=round(departure, 2),
                arrival_time=round(arrival, 2),
                strategy_name=seg_result.strategy_name,
                weather_display=seg_result.weather_display,
            )
            segments.append(seg_info)
            current_time = arrival

        delay_prob = self.compute_delay_probability(
            path_result.total_time, deadline_hours,
            path_result.risk_count, path_result.station_count,
        )

        return PlanInfo(
            plan_type=plan_type,
            plan_type_display=PLAN_TYPE_DISPLAY.get(plan_type, plan_type),
            total_time=path_result.total_time,
            total_distance=path_result.total_distance,
            risk_count=path_result.risk_count,
            station_count=path_result.station_count,
            is_delay_risk=delay_prob >= self.delay_risk_threshold,
            delay_probability=delay_prob,
            segments=segments,
        )

    def generate_all_plans(
        self,
        roads: List[RoadInfo],
        origin_id: int,
        destination_id: int,
        priority: int = 1,
        strategy: Optional[StrategyInfo] = None,
        departure_offset: float = 0.0,
        deadline_hours: Optional[float] = None,
        max_paths: int = 5,
    ) -> Result[List[PlanInfo]]:
        """
        生成所有递送方案

        Args:
            roads: 所有道路
            origin_id: 起点驿站ID
            destination_id: 终点驿站ID
            priority: 优先级
            strategy: 换马策略
            departure_offset: 出发时间偏移
            deadline_hours: 要求时限
            max_paths: 最大方案数

        Returns:
            Result[List[PlanInfo]] 方案列表
        """
        if origin_id == destination_id:
            return Result.fail('起点和终点不能相同', error_code='INVALID_INPUT')

        path_results = self.route_engine.find_all_paths(
            roads, origin_id, destination_id,
            priority=priority, strategy=strategy,
            max_paths=max_paths,
        )

        if not path_results:
            return Result.fail(
                f'无法找到连通路线',
                error_code='ROUTE_NOT_FOUND',
                details={'origin_id': origin_id, 'destination_id': destination_id},
            )

        plans = []
        for plan_type, path_result in path_results:
            if not path_result.is_valid:
                continue
            plan = self.generate_plan_from_path(
                plan_type=plan_type,
                path_result=path_result,
                departure_offset=departure_offset,
                deadline_hours=deadline_hours,
            )
            plans.append(plan)

        if not plans:
            return Result.fail('没有可用的递送方案', error_code='NO_VALID_PLAN')

        return Result.ok(plans)

    def get_plan_comparison_data(self, plans: List[PlanInfo]) -> List[Dict[str, Any]]:
        """
        获取方案对比数据（用于图表展示）

        Args:
            plans: 方案列表

        Returns:
            对比数据列表
        """
        comparison = []
        for plan in plans:
            seg_data = []
            for seg in plan.segments:
                seg_data.append({
                    'order': seg.order,
                    'from': seg.from_station_code,
                    'to': seg.to_station_code,
                    'distance': seg.distance,
                    'segment_time': seg.segment_time,
                    'travel_time': seg.travel_time,
                    'horse_change_time': seg.horse_change_time,
                    'process_time': seg.process_time,
                    'is_high_risk': seg.is_high_risk,
                    'departure_time': seg.departure_time,
                    'arrival_time': seg.arrival_time,
                    'strategy_name': seg.strategy_name,
                    'weather_display': seg.weather_display,
                })
            comparison.append({
                'plan_type': plan.plan_type,
                'plan_type_display': plan.plan_type_display,
                'total_time': plan.total_time,
                'total_distance': plan.total_distance,
                'risk_count': plan.risk_count,
                'station_count': plan.station_count,
                'is_delay_risk': plan.is_delay_risk,
                'delay_probability': plan.delay_probability,
                'segments': seg_data,
            })
        return comparison

    def get_gantt_data(self, plans: List[PlanInfo]) -> List[Dict[str, Any]]:
        """
        获取甘特图数据

        Args:
            plans: 方案列表

        Returns:
            甘特图数据列表
        """
        gantt = []
        for plan in plans:
            for seg in plan.segments:
                gantt.append({
                    'plan_type': plan.plan_type,
                    'plan_type_display': plan.plan_type_display,
                    'task': f'{seg.from_station_code}→{seg.to_station_code}',
                    'start': seg.departure_time or 0,
                    'end': seg.arrival_time or 0,
                    'is_high_risk': seg.is_high_risk,
                    'segment_time': seg.segment_time,
                })
        return gantt

    def get_analysis_data(self, plan: PlanInfo) -> Dict[str, Any]:
        """
        获取分析图表数据

        Args:
            plan: 方案信息

        Returns:
            分析数据字典
        """
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

        for seg in plan.segments:
            chart_data['labels'].append(f'{seg.from_station_code}→{seg.to_station_code}')
            chart_data['travel_times'].append(seg.travel_time)
            chart_data['horse_change_times'].append(seg.horse_change_time)
            chart_data['process_times'].append(seg.process_time)
            chart_data['total_times'].append(seg.segment_time)
            chart_data['risks'].append(1 if seg.is_high_risk else 0)
            chart_data['distances'].append(seg.distance)
            chart_data['departures'].append(seg.departure_time or 0)
            chart_data['arrivals'].append(seg.arrival_time or 0)

        return chart_data


_default_plan_engine = PlanEngine()


def compute_delay_probability(
    total_time: float,
    deadline_hours: Optional[float],
    risk_count: int,
    station_count: int,
) -> float:
    """便捷函数 - 计算延误概率"""
    return _default_plan_engine.compute_delay_probability(
        total_time, deadline_hours, risk_count, station_count,
    )


def generate_all_plans(
    roads: List[RoadInfo],
    origin_id: int,
    destination_id: int,
    priority: int = 1,
    strategy: Optional[StrategyInfo] = None,
    departure_offset: float = 0.0,
    deadline_hours: Optional[float] = None,
) -> Result[List[PlanInfo]]:
    """便捷函数 - 生成所有方案"""
    return _default_plan_engine.generate_all_plans(
        roads=roads,
        origin_id=origin_id,
        destination_id=destination_id,
        priority=priority,
        strategy=strategy,
        departure_offset=departure_offset,
        deadline_hours=deadline_hours,
    )
