"""gRPC deadline budget and capped, jittered retries for READ-ONLY calls.

No automatic retry for Mutation RPCs: a timeout may follow a successful DB
commit. The Lab-4 operationId receipts and Kafka outbox make manual replays safe.
"""
import random
import time
import grpc
from app.resilience.telemetry import emit, elapsed_ms

READ_ONLY = frozenset({
    'GetMe','ListUsers','GetStudent','ReadCredentialForAuth',
    'SearchTeachers','GetTeacher','ListSubjects','GetTeacherSubjects','GetTeacherMetrics',
    'GetTeachingOffer','ListAvailableSlots','GetMySchedule','ListLessons',
    'ListMyBookings','GetSlot','GetLesson','GetLessonSnapshot','GetBookingSnapshot',
    'ListMyPayments','ListReviews','GetRating','ListNotifications','GetPlatformAnalytics',
    'ValidateSession',
})
TRANSIENT = frozenset({grpc.StatusCode.UNAVAILABLE,
                       grpc.StatusCode.DEADLINE_EXCEEDED,
                       grpc.StatusCode.RESOURCE_EXHAUSTED})


def call_with_policy(call, *, service, method, read_only=None, budget=None,
                     clock=time.monotonic, pause=time.sleep, jitter=random.uniform):
    read = method in READ_ONLY if read_only is None else bool(read_only)
    max_attempts = 3 if read else 1
    time_budget = float(budget if budget is not None else (9 if read else 12))
    started = clock()
    deadline = started + time_budget
    for attempt in range(1, max_attempts + 1):
        remaining = deadline - clock()
        if remaining <= 0:
            # A prior gRPC RpcError is raised directly when the deadline expires.
            raise TimeoutError(f'{service}/{method}: total deadline exceeded')
        per_attempt = min(3.5 if read else 12.0, remaining)
        try:
            result = call(timeout=per_attempt)
            emit('grpc_client',service=service,method=method,attempt=attempt,
                 result='ok',elapsed_ms=elapsed_ms(started))
            return result
        except grpc.RpcError as exc:
            code = exc.code()
            will_retry = read and code in TRANSIENT and attempt < max_attempts
            delay = (min(.15 * (2 ** (attempt - 1)), .7) + jitter(0, .08)) if will_retry else 0
            if will_retry and (deadline - clock()) <= delay + .01:
                will_retry = False
            emit('grpc_client',level='warning',service=service,method=method,
                 attempt=attempt,grpc_code=getattr(code,'name',str(code)),
                 result='retry' if will_retry else 'failed',elapsed_ms=elapsed_ms(started))
            if not will_retry:
                raise
            pause(delay)
    raise AssertionError('Unreachable gRPC retry state')
