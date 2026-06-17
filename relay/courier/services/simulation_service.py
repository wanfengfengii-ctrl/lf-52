from typing import Dict, Any
from collections import defaultdict

from django.utils import timezone

from ..models import (
    SimulationRun, SimTask, SimBottleneckStation,
)
from ..core.result import Result
from ..core.exceptions import SimulationError


class SimulationService:
    """仿真服务 - 仿真业务流程编排"""

    def run_simulation(self, simulation_run_id: int) -> Result[Dict[str, Any]]:
        """
        运行仿真

        Args:
            simulation_run_id: 仿真运行ID

        Returns:
            Result 包含运行结果
        """
        from ..simulation_engine import run_simulation as _run_simulation

        try:
            result = _run_simulation(simulation_run_id)
            if result.get('success'):
                return Result.ok({
                    'total_tasks': result.get('total_tasks', 0),
                    'completed_tasks': result.get('completed_tasks', 0),
                })
            else:
                return Result.fail(
                    error=result.get('error', '未知错误'),
                    error_code='SIMULATION_FAILED',
                )
        except Exception as e:
            return Result.from_exception(e)

    def get_simulation_result_data(self, sim_run_id: int) -> Result[Dict[str, Any]]:
        """
        获取仿真结果数据

        Args:
            sim_run_id: 仿真运行ID

        Returns:
            Result 包含结果数据
        """
        from ..simulation_engine import get_simulation_result_data as _get_result

        try:
            sim_run = SimulationRun.objects.get(pk=sim_run_id)
            if sim_run.status != 'completed':
                return Result.fail('仿真尚未完成运行', error_code='SIMULATION_NOT_COMPLETED')

            result_data = _get_result(sim_run_id)
            return Result.ok(result_data)
        except SimulationRun.DoesNotExist:
            return Result.fail('仿真不存在', error_code='SIMULATION_NOT_FOUND')
        except Exception as e:
            return Result.from_exception(e)


_default_simulation_service = SimulationService()


def run_simulation(simulation_run_id: int) -> Dict[str, Any]:
    """便捷函数 - 运行仿真（保持向后兼容）"""
    result = _default_simulation_service.run_simulation(simulation_run_id)
    if result.is_success:
        return {'success': True, **result.data}
    return {'success': False, 'error': result.error}


def get_simulation_result_data(sim_run_id: int) -> Dict[str, Any]:
    """便捷函数 - 获取仿真结果数据（保持向后兼容）"""
    from ..simulation_engine import get_simulation_result_data as _get_result
    return _get_result(sim_run_id)
