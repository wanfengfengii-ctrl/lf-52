import heapq
import random
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Any

from ..core.datatypes import RoadInfo, StrategyInfo, SegmentResult, PathResult
from ..core.exceptions import RouteNotFoundError
from .segment_engine import SegmentEngine, calculate_segment_time


class RouteEngine:
    """路线计算引擎 - 纯函数化，基于图结构计算最短路径"""

    def __init__(self, segment_engine: SegmentEngine = None):
        self.segment_engine = segment_engine or SegmentEngine()

    def build_graph(self, roads: List[RoadInfo]) -> Dict[int, List[Tuple[int, RoadInfo]]]:
        """
        从道路列表构建邻接图

        Args:
            roads: 道路信息列表

        Returns:
            邻接表 {from_station_id: [(to_station_id, RoadInfo), ...]}
        """
        graph = defaultdict(list)
        for road in roads:
            graph[road.from_station_id].append((road.to_station_id, road))
        return graph

    def dijkstra(
        self,
        graph: Dict[int, List[Tuple[int, RoadInfo]]],
        origin_id: int,
        destination_id: int,
        priority: int = 1,
        strategy: Optional[StrategyInfo] = None,
        optimize: str = 'time',
        station_process_times: Dict[int, float] = None,
    ) -> Optional[Tuple[List[RoadInfo], List[SegmentResult]]]:
        """
        Dijkstra 最短路径算法

        Args:
            graph: 邻接图
            origin_id: 起点驿站ID
            destination_id: 终点驿站ID
            priority: 优先级
            strategy: 换马策略
            optimize: 优化目标 ('time', 'safe', 'balanced')
            station_process_times: 各驿站处理时间映射 {station_id: process_time}

        Returns:
            (路径道路列表, 路段结果列表) 或 None（无路径）
        """
        if origin_id == destination_id:
            return [], []

        station_process_times = station_process_times or {}

        dist = {origin_id: 0.0}
        risk = {origin_id: 0.0}
        prev = {}
        pq = [(0.0, 0.0, origin_id)]
        visited = set()

        while pq:
            current_cost, current_risk, current = heapq.heappop(pq)
            if current in visited:
                continue
            visited.add(current)
            if current == destination_id:
                break

            for next_id, road in graph.get(current, []):
                process_time = station_process_times.get(road.to_station_id, 0.0)
                seg_result = self.segment_engine.calculate(
                    road=road,
                    priority=priority,
                    strategy=strategy,
                    process_time=process_time,
                )

                if optimize == 'time':
                    edge_cost = seg_result.total_time
                elif optimize == 'safe':
                    edge_cost = seg_result.risk_score * 10 + seg_result.total_time * 0.1
                elif optimize == 'balanced':
                    edge_cost = seg_result.total_time + seg_result.risk_score * 2.0
                else:
                    edge_cost = seg_result.total_time

                new_cost = dist[current] + edge_cost
                new_risk = risk.get(current, 0.0) + seg_result.risk_score

                if next_id not in dist or new_cost < dist[next_id]:
                    dist[next_id] = new_cost
                    risk[next_id] = new_risk
                    prev[next_id] = (current, road, seg_result)
                    heapq.heappush(pq, (new_cost, new_risk, next_id))

        if destination_id not in prev:
            return None

        path_roads = []
        path_results = []
        current = destination_id
        while current != origin_id and current in prev:
            prev_station, road, seg_result = prev[current]
            path_roads.append(road)
            path_results.append(seg_result)
            current = prev_station

        path_roads.reverse()
        path_results.reverse()
        return path_roads, path_results

    def find_path(
        self,
        roads: List[RoadInfo],
        origin_id: int,
        destination_id: int,
        optimize: str = 'time',
        priority: int = 1,
        strategy: Optional[StrategyInfo] = None,
        station_process_times: Dict[int, float] = None,
    ) -> Optional[PathResult]:
        """
        查找单一路径

        Args:
            roads: 所有道路
            origin_id: 起点
            destination_id: 终点
            optimize: 优化目标
            priority: 优先级
            strategy: 换马策略
            station_process_times: 驿站处理时间映射

        Returns:
            PathResult 或 None
        """
        graph = self.build_graph(roads)
        result = self.dijkstra(
            graph, origin_id, destination_id,
            priority=priority, strategy=strategy,
            optimize=optimize,
            station_process_times=station_process_times,
        )
        if result is None:
            return None

        path_roads, path_results = result
        total_time = sum(r.total_time for r in path_results)
        total_distance = sum(r.distance for r in path_results)
        risk_count = sum(1 for r in path_results if r.is_high_risk)

        return PathResult(
            path_roads=path_roads,
            path_results=path_results,
            total_time=round(total_time, 2),
            total_distance=round(total_distance, 2),
            risk_count=risk_count,
            station_count=len(path_roads),
        )

    def find_all_paths(
        self,
        roads: List[RoadInfo],
        origin_id: int,
        destination_id: int,
        priority: int = 1,
        strategy: Optional[StrategyInfo] = None,
        max_paths: int = 5,
        station_process_times: Dict[int, float] = None,
    ) -> List[Tuple[str, PathResult]]:
        """
        查找多种策略的路径

        Args:
            roads: 所有道路
            origin_id: 起点
            destination_id: 终点
            priority: 优先级
            strategy: 换马策略
            max_paths: 最大路径数
            station_process_times: 驿站处理时间映射

        Returns:
            [(方案类型, PathResult), ...]
        """
        graph = self.build_graph(roads)
        results = []

        strategies = [
            ('fastest', 'time'),
            ('safest', 'safe'),
            ('balanced', 'balanced'),
        ]

        for plan_type, optimize in strategies:
            result = self.dijkstra(
                graph, origin_id, destination_id,
                priority=priority, strategy=strategy,
                optimize=optimize,
                station_process_times=station_process_times,
            )
            if result:
                path_roads, path_results = result
                total_time = sum(r.total_time for r in path_results)
                total_distance = sum(r.distance for r in path_results)
                risk_count = sum(1 for r in path_results if r.is_high_risk)

                path_result = PathResult(
                    path_roads=path_roads,
                    path_results=path_results,
                    total_time=round(total_time, 2),
                    total_distance=round(total_distance, 2),
                    risk_count=risk_count,
                    station_count=len(path_roads),
                )
                results.append((plan_type, path_result))

        if len(results) < max_paths:
            result = self.dijkstra(
                graph, origin_id, destination_id,
                priority=priority, strategy=strategy,
                optimize='time',
                station_process_times=station_process_times,
            )
            if result:
                base_roads, _ = result
                if base_roads and len(base_roads) >= 3:
                    try:
                        mid_idx = len(base_roads) // 2
                        skip_road_id = base_roads[mid_idx].id
                        filtered_graph = defaultdict(list)
                        for from_id, edges in graph.items():
                            for to_id, road in edges:
                                if road.id != skip_road_id:
                                    filtered_graph[from_id].append((to_id, road))
                        alt_result = self.dijkstra(
                            filtered_graph, origin_id, destination_id,
                            priority=priority, strategy=strategy,
                            optimize='time',
                            station_process_times=station_process_times,
                        )
                        if alt_result:
                            alt_roads, alt_results = alt_result
                            existing_road_ids = set(r.id for _, pr in results for r in pr.path_roads)
                            if any(r.id not in existing_road_ids for r in alt_roads):
                                total_time = sum(r.total_time for r in alt_results)
                                total_distance = sum(r.distance for r in alt_results)
                                risk_count = sum(1 for r in alt_results if r.is_high_risk)
                                alt_path_result = PathResult(
                                    path_roads=alt_roads,
                                    path_results=alt_results,
                                    total_time=round(total_time, 2),
                                    total_distance=round(total_distance, 2),
                                    risk_count=risk_count,
                                    station_count=len(alt_roads),
                                )
                                results.append(('alternative', alt_path_result))
                    except Exception:
                        pass

        return results


_default_route_engine = RouteEngine()


def build_graph(roads: List[RoadInfo]) -> Dict[int, List[Tuple[int, RoadInfo]]]:
    """便捷函数 - 构建图"""
    return _default_route_engine.build_graph(roads)


def dijkstra(
    graph: Dict[int, List[Tuple[int, RoadInfo]]],
    origin_id: int,
    destination_id: int,
    priority: int = 1,
    strategy: Optional[StrategyInfo] = None,
    optimize: str = 'time',
) -> Optional[Tuple[List[RoadInfo], List[SegmentResult]]]:
    """便捷函数 - Dijkstra 算法"""
    return _default_route_engine.dijkstra(
        graph, origin_id, destination_id,
        priority=priority, strategy=strategy, optimize=optimize,
    )


def find_path(
    roads: List[RoadInfo],
    origin_id: int,
    destination_id: int,
    optimize: str = 'time',
    priority: int = 1,
    strategy: Optional[StrategyInfo] = None,
) -> Optional[PathResult]:
    """便捷函数 - 查找单一路径"""
    return _default_route_engine.find_path(
        roads, origin_id, destination_id,
        optimize=optimize, priority=priority, strategy=strategy,
    )


def find_all_paths(
    roads: List[RoadInfo],
    origin_id: int,
    destination_id: int,
    priority: int = 1,
    strategy: Optional[StrategyInfo] = None,
    max_paths: int = 5,
) -> List[Tuple[str, PathResult]]:
    """便捷函数 - 查找多种策略的路径"""
    return _default_route_engine.find_all_paths(
        roads, origin_id, destination_id,
        priority=priority, strategy=strategy, max_paths=max_paths,
    )
