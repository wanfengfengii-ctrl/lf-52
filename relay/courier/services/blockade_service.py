from typing import Dict, Any

from django.utils import timezone

from ..models import BlockadeDrill
from ..core.result import Result
from ..core.exceptions import BlockadeError


class BlockadeService:
    """封锁推演服务 - 封锁推演业务流程编排"""

    def run_blockade_drill(self, drill_id: int) -> Result[Dict[str, Any]]:
        """
        运行封锁推演

        Args:
            drill_id: 推演ID

        Returns:
            Result 包含运行结果
        """
        from ..blockade_engine import run_blockade_drill as _run_drill

        try:
            result = _run_drill(drill_id)
            if result.get('success'):
                return Result.ok({
                    'drill_id': result.get('drill_id', drill_id),
                })
            else:
                return Result.fail(
                    error=result.get('error', '未知错误'),
                    error_code='BLOCKADE_DRILL_FAILED',
                )
        except Exception as e:
            return Result.from_exception(e)

    def get_blockade_drill_data(self, drill_id: int) -> Result[Dict[str, Any]]:
        """
        获取封锁推演结果数据

        Args:
            drill_id: 推演ID

        Returns:
            Result 包含结果数据
        """
        from ..blockade_engine import get_blockade_drill_data as _get_data

        try:
            drill = BlockadeDrill.objects.get(pk=drill_id)
            if drill.status != 'completed':
                return Result.fail('推演尚未完成', error_code='DRILL_NOT_COMPLETED')

            result_data = _get_data(drill_id)
            return Result.ok(result_data)
        except BlockadeDrill.DoesNotExist:
            return Result.fail('推演不存在', error_code='DRILL_NOT_FOUND')
        except Exception as e:
            return Result.from_exception(e)


_default_blockade_service = BlockadeService()


def run_blockade_drill(drill_id: int) -> Dict[str, Any]:
    """便捷函数 - 运行封锁推演（保持向后兼容）"""
    result = _default_blockade_service.run_blockade_drill(drill_id)
    if result.is_success:
        return {'success': True, **result.data}
    return {'success': False, 'error': result.error}


def get_blockade_drill_data(drill_id: int) -> Dict[str, Any]:
    """便捷函数 - 获取封锁推演数据（保持向后兼容）"""
    from ..blockade_engine import get_blockade_drill_data as _get_data
    return _get_data(drill_id)
