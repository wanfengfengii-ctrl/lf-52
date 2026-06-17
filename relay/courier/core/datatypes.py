from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class StationInfo:
    id: int
    code: str
    name: str
    latitude: float
    longitude: float
    capacity: int = 5
    window_count: int = 1
    process_time: float = 0.2
    queue_rule: str = 'priority_class'
    description: str = ''

    @classmethod
    def from_model(cls, station) -> 'StationInfo':
        return cls(
            id=station.pk,
            code=station.code,
            name=station.name,
            latitude=station.latitude,
            longitude=station.longitude,
            capacity=station.capacity,
            window_count=station.window_count,
            process_time=station.process_time,
            queue_rule=station.queue_rule,
            description=station.description or '',
        )


@dataclass
class RoadInfo:
    id: int
    from_station_id: int
    to_station_id: int
    from_station_code: str = ''
    to_station_code: str = ''
    distance: float = 0.0
    slope: float = 0.0
    grade: int = 2

    @classmethod
    def from_model(cls, road) -> 'RoadInfo':
        return cls(
            id=road.pk,
            from_station_id=road.from_station_id,
            to_station_id=road.to_station_id,
            from_station_code=road.from_station.code if road.from_station else '',
            to_station_code=road.to_station.code if road.to_station else '',
            distance=road.distance,
            slope=road.slope or 0.0,
            grade=road.grade,
        )


@dataclass
class StrategyInfo:
    id: Optional[int]
    name: str
    interval_distance: float
    change_time: float = 0.5
    description: str = ''

    @classmethod
    def from_model(cls, strategy) -> Optional['StrategyInfo']:
        if strategy is None:
            return None
        return cls(
            id=strategy.pk,
            name=strategy.name,
            interval_distance=strategy.interval_distance,
            change_time=strategy.change_time or 0.5,
            description=strategy.description or '',
        )


@dataclass
class SegmentResult:
    travel_time: float = 0.0
    horse_change_time: float = 0.0
    process_time: float = 0.0
    total_time: float = 0.0
    is_high_risk: bool = False
    risk_score: float = 0.0
    speed: float = 0.0
    distance: float = 0.0
    grade: int = 2
    slope: float = 0.0
    weather_type: Optional[int] = None
    strategy_name: str = ''
    weather_display: str = '晴朗'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'travel_time': round(self.travel_time, 2),
            'horse_change_time': round(self.horse_change_time, 2),
            'process_time': round(self.process_time, 2),
            'total_time': round(self.total_time, 2),
            'is_high_risk': self.is_high_risk,
            'risk_score': round(self.risk_score, 2),
            'speed': round(self.speed, 2),
            'distance': self.distance,
            'grade': self.grade,
            'slope': self.slope,
        }


@dataclass
class PathResult:
    path_roads: List[RoadInfo] = field(default_factory=list)
    path_results: List[SegmentResult] = field(default_factory=list)
    total_time: float = 0.0
    total_distance: float = 0.0
    risk_count: int = 0
    station_count: int = 0

    @property
    def is_valid(self) -> bool:
        return len(self.path_roads) > 0


@dataclass
class PlanSegmentInfo:
    order: int
    road_id: int
    from_station_code: str
    to_station_code: str
    distance: float
    segment_time: float
    travel_time: float
    horse_change_time: float
    process_time: float
    is_high_risk: bool
    departure_time: Optional[float] = None
    arrival_time: Optional[float] = None
    strategy_name: str = ''
    weather_display: str = '晴朗'


@dataclass
class PlanInfo:
    plan_type: str
    plan_type_display: str
    total_time: float
    total_distance: float
    risk_count: int
    station_count: int
    is_delay_risk: bool = False
    delay_probability: float = 0.0
    segments: List[PlanSegmentInfo] = field(default_factory=list)
