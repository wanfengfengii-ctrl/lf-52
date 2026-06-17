import math
from typing import Optional, Dict, Any

from ..core.datatypes import RoadInfo, StrategyInfo, SegmentResult
from ..core.exceptions import ValidationError


BASE_SPEED_LI_PER_SHICHEN = 60.0

GRADE_SPEED_FACTOR = {
    1: 1.0,
    2: 0.85,
    3: 0.65,
    4: 0.45,
    5: 0.25,
}

PRIORITY_SPEED_FACTOR = {
    1: 1.0,
    2: 1.4,
    3: 2.0,
}

HIGH_RISK_THRESHOLD = 2.5
RISK_PENALTY_FACTOR = 2.0

WEATHER_SEVERITY_MAP = {
    1: 1.0, 2: 1.1, 3: 1.3, 4: 1.6,
    5: 2.0, 6: 1.4, 7: 1.8, 8: 2.5,
}

WEATHER_DISPLAY_MAP = {
    1: '晴朗', 2: '多云', 3: '小雨', 4: '大雨',
    5: '暴雨', 6: '小雪', 7: '大雪', 8: '暴雪',
}


class SegmentEngine:
    """路段时间计算引擎 - 纯函数化，不依赖 ORM"""

    def __init__(
        self,
        base_speed: float = BASE_SPEED_LI_PER_SHICHEN,
        grade_factors: Dict[int, float] = None,
        priority_factors: Dict[int, float] = None,
        high_risk_threshold: float = HIGH_RISK_THRESHOLD,
        weather_severity_map: Dict[int, float] = None,
    ):
        self.base_speed = base_speed
        self.grade_factors = grade_factors or GRADE_SPEED_FACTOR
        self.priority_factors = priority_factors or PRIORITY_SPEED_FACTOR
        self.high_risk_threshold = high_risk_threshold
        self.weather_severity_map = weather_severity_map or WEATHER_SEVERITY_MAP

    def calculate(
        self,
        road: RoadInfo,
        weather_type: Optional[int] = None,
        priority: int = 1,
        strategy: Optional[StrategyInfo] = None,
        process_time: float = 0.0,
    ) -> SegmentResult:
        """
        计算单个路段的时间

        Args:
            road: 道路信息
            weather_type: 天气类型（1-8），None 表示使用默认晴朗
            priority: 优先级（1-3）
            strategy: 换马策略
            process_time: 终点驿站处理时间

        Returns:
            SegmentResult 路段计算结果
        """
        speed = self.base_speed

        grade_factor = self.grade_factors.get(road.grade, 0.85)
        speed *= grade_factor

        slope = road.slope or 0
        if slope > 0:
            slope_factor = max(0.2, 1.0 - slope * 0.03)
            speed *= slope_factor

        if weather_type:
            weather_factor = self.weather_severity_map.get(weather_type, 1.0)
            speed /= weather_factor

        priority_factor = self.priority_factors.get(priority, 1.0)
        speed *= priority_factor

        if speed <= 0:
            speed = 0.1

        travel_time = road.distance / speed

        horse_change_time = 0.0
        if strategy and strategy.interval_distance and strategy.interval_distance > 0:
            num_changes = math.floor(road.distance / strategy.interval_distance)
            horse_change_time = num_changes * (strategy.change_time or 0)

        total_time = travel_time + horse_change_time + process_time

        is_high_risk = False
        risk_score = 0.0

        if weather_type:
            wf = self.weather_severity_map.get(weather_type, 1.0)
            if wf >= self.high_risk_threshold:
                is_high_risk = True
                risk_score += 1.0

        if road.grade >= 5:
            is_high_risk = True
            risk_score += 0.8

        if slope > 20:
            is_high_risk = True
            risk_score += 0.6
        elif slope > 10:
            risk_score += 0.3

        weather_display = WEATHER_DISPLAY_MAP.get(weather_type, '晴朗') if weather_type else '晴朗'
        strategy_name = strategy.name if strategy else '默认策略'

        return SegmentResult(
            travel_time=round(travel_time, 2),
            horse_change_time=round(horse_change_time, 2),
            process_time=round(process_time, 2),
            total_time=round(total_time, 2),
            is_high_risk=is_high_risk,
            risk_score=round(risk_score, 2),
            speed=round(speed, 2),
            distance=road.distance,
            grade=road.grade,
            slope=slope,
            weather_type=weather_type,
            strategy_name=strategy_name,
            weather_display=weather_display,
        )

    def validate_input(self, road: RoadInfo, priority: int = 1) -> None:
        """验证输入参数"""
        if not road or not road.id:
            raise ValidationError('道路信息不能为空')
        if road.distance <= 0:
            raise ValidationError(f'道路长度必须大于0，当前值: {road.distance}')
        if priority not in self.priority_factors:
            raise ValidationError(f'无效的优先级: {priority}')


_default_segment_engine = SegmentEngine()


def calculate_segment_time(
    road: RoadInfo,
    weather_type: Optional[int] = None,
    priority: int = 1,
    strategy: Optional[StrategyInfo] = None,
    process_time: float = 0.0,
) -> SegmentResult:
    """
    便捷函数 - 使用默认引擎计算路段时间

    为保持向后兼容，此函数签名与原有函数类似，但输入输出均为数据类
    """
    return _default_segment_engine.calculate(
        road=road,
        weather_type=weather_type,
        priority=priority,
        strategy=strategy,
        process_time=process_time,
    )
