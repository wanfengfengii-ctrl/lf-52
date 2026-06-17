from typing import List, Dict, Any, Optional

from ..models import (
    HorseChangeStrategy, DeliveryTask, DeliverySegment,
    Station,
)
from ..core.datatypes import RoadInfo, StrategyInfo
from ..engines.segment_engine import SegmentEngine


class AnalysisService:
    """分析服务 - 数据分析与可视化"""

    def __init__(self, segment_engine: SegmentEngine = None):
        self.segment_engine = segment_engine or SegmentEngine()

    def get_strategy_comparison(self, sample_task: DeliveryTask) -> List[Dict[str, Any]]:
        """
        获取策略对比数据

        Args:
            sample_task: 样例任务

        Returns:
            策略对比数据列表
        """
        all_strategies = HorseChangeStrategy.objects.all()
        comparison_data = []

        segments = DeliverySegment.objects.filter(
            task=sample_task
        ).select_related('road').all()

        for strategy in all_strategies:
            strat_info = StrategyInfo.from_model(strategy)
            total = 0
            for seg in segments:
                road_info = RoadInfo.from_model(seg.road)
                result = self.segment_engine.calculate(
                    road=road_info,
                    priority=sample_task.priority,
                    strategy=strat_info,
                )
                total += result.total_time
            comparison_data.append({
                'name': strategy.name,
                'time': round(total, 2),
            })

        return comparison_data

    def get_delay_warning_data(self) -> List[Dict[str, Any]]:
        """
        获取延误预警任务数据

        Returns:
            延误数据列表
        """
        delay_warning_tasks = DeliveryTask.objects.filter(
            delay_warning=True
        ).select_related('origin', 'destination')

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

        return delay_data

    def get_analysis_dashboard_data(self) -> Dict[str, Any]:
        """
        获取分析仪表盘数据

        Returns:
            仪表盘数据字典
        """
        tasks = DeliveryTask.objects.select_related('origin', 'destination', 'strategy').all()

        from .delivery_service import DeliveryService
        delivery_service = DeliveryService()

        task_data = []
        for task in tasks:
            if task.estimated_hours:
                chart = delivery_service.get_task_analysis_data(task)
                plan_comparison = delivery_service.get_plan_comparison_for_task(task)
                task_data.append({
                    'task': task,
                    'chart_data': chart,
                    'plan_comparison': plan_comparison,
                })

        comparison_data = []
        all_strategies = HorseChangeStrategy.objects.all()
        if all_strategies.count() >= 2 and tasks.exists():
            sample_task = tasks.first()
            if sample_task:
                comparison_data = self.get_strategy_comparison(sample_task)

        delay_data = self.get_delay_warning_data()

        return {
            'task_data': task_data,
            'comparison_data': comparison_data,
            'comparison_available': len(comparison_data) >= 2,
            'delay_data': delay_data,
            'delay_count': len(delay_data),
        }


_default_analysis_service = AnalysisService()


def get_strategy_comparison(sample_task: DeliveryTask) -> List[Dict[str, Any]]:
    """便捷函数 - 获取策略对比"""
    return _default_analysis_service.get_strategy_comparison(sample_task)


def get_delay_warning_data() -> List[Dict[str, Any]]:
    """便捷函数 - 获取延误预警数据"""
    return _default_analysis_service.get_delay_warning_data()


def get_analysis_dashboard_data() -> Dict[str, Any]:
    """便捷函数 - 获取分析仪表盘数据"""
    return _default_analysis_service.get_analysis_dashboard_data()
