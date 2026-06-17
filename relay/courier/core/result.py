from typing import Generic, TypeVar, Optional, Any, Dict
from dataclasses import dataclass, field

from .exceptions import CourierError

T = TypeVar('T')


@dataclass
class Result(Generic[T]):
    """统一结果包装类"""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: T = None, **details) -> 'Result[T]':
        return cls(success=True, data=data, details=details)

    @classmethod
    def fail(cls, error: str = '', error_code: str = 'ERROR', data: T = None, **details) -> 'Result[T]':
        return cls(success=False, error=error, error_code=error_code, data=data, details=details)

    @classmethod
    def from_exception(cls, exc: Exception) -> 'Result[T]':
        if isinstance(exc, CourierError):
            return cls.fail(
                error=exc.message,
                error_code=exc.code,
                details=exc.details,
            )
        return cls.fail(error=str(exc), error_code='UNKNOWN_ERROR')

    @property
    def is_success(self) -> bool:
        return self.success

    @property
    def is_failure(self) -> bool:
        return not self.success

    def to_dict(self) -> Dict[str, Any]:
        result = {
            'success': self.success,
        }
        if self.success:
            result['data'] = self.data
            if self.details:
                result.update(self.details)
        else:
            result['error'] = self.error
            result['error_code'] = self.error_code
            if self.details:
                result['details'] = self.details
        return result

    def unwrap(self) -> T:
        if self.is_failure:
            raise CourierError(self.error or 'Unknown error', code=self.error_code or 'ERROR')
        return self.data


SuccessResult = Result.ok
FailureResult = Result.fail
