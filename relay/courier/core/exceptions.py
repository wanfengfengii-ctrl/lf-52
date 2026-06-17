class CourierError(Exception):
    """业务异常基类"""

    def __init__(self, message: str = '', code: str = 'COURIER_ERROR', details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            'error': self.message,
            'code': self.code,
            'details': self.details,
        }


class ValidationError(CourierError):
    """数据验证错误"""

    def __init__(self, message: str = '数据验证失败', details: dict = None):
        super().__init__(message, code='VALIDATION_ERROR', details=details)


class RouteNotFoundError(CourierError):
    """路线未找到错误"""

    def __init__(self, origin_id: int = None, dest_id: int = None, message: str = None):
        msg = message or f'无法找到从 {origin_id} 到 {dest_id} 的连通路线'
        details = {'origin_id': origin_id, 'dest_id': dest_id}
        super().__init__(msg, code='ROUTE_NOT_FOUND', details=details)


class SimulationError(CourierError):
    """仿真错误"""

    def __init__(self, message: str = '仿真运行失败', details: dict = None):
        super().__init__(message, code='SIMULATION_ERROR', details=details)


class BlockadeError(CourierError):
    """封锁推演错误"""

    def __init__(self, message: str = '封锁推演失败', details: dict = None):
        super().__init__(message, code='BLOCKADE_ERROR', details=details)
