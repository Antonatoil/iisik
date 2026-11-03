"""Network-backed MOCK adapter. Same MockRpcPorts API as labs 3/4.

No gRPC or Kafka; transport sends allowlisted HTTP requests to independently
running service processes. Gateway imports no service/repository modules.
"""
import os
import httpx
from app.core.errors import fail
from app.transport.rpc_registry import RPC_METHODS, SERVICE_NAMES
from app.transport.rpc_codec import to_wire, from_wire
from app.transport import workflows


class MockRpcPorts:
    # These orchestrate several services and are deliberately on the gateway side.
    RegisterUser = staticmethod(workflows.register)
    LoginUser = staticmethod(workflows.login)
    UpdateTeacherProfile = staticmethod(workflows.update_teacher_profile)
    SetAvailability = staticmethod(workflows.set_availability)
    BookLesson = staticmethod(workflows.book_lesson)
    ChangeLesson = staticmethod(workflows.change_lesson)
    RegisterPayment = staticmethod(workflows.register_payment)
    AddReview = staticmethod(workflows.add_review)
    MarkNotificationRead = staticmethod(workflows.mark_notification_read)
    SetUserStatus = staticmethod(workflows.set_user_status)
    ManageSubject = staticmethod(workflows.manage_subject)

    def __getattr__(self, method):
        if method not in RPC_METHODS:
            raise AttributeError(method)
        return lambda *args, **kwargs: self._request(method, args, kwargs)

    @staticmethod
    def _request(method, args, kwargs):
        token = os.environ.get('RPC_SHARED_KEY')
        if not token:
            fail('CONFIGURATION_ERROR', 'Mock RPC shared secret is missing')
        owner = RPC_METHODS[method][0]
        url = 'http://' + SERVICE_NAMES[owner] + ':8100/mock/' + method
        try:
            with httpx.Client(timeout=httpx.Timeout(15.0, connect=3.0), trust_env=False) as client:
                response = client.post(url, json={'args': to_wire(args), 'kwargs': to_wire(kwargs)},
                                       headers={'X-Mock-Token': token})
            if response.status_code >= 500:
                fail('SERVICE_UNAVAILABLE', f'{SERVICE_NAMES[owner]} service returned an error')
            try:
                data = response.json()
            except ValueError:
                fail('SERVICE_UNAVAILABLE', 'Invalid response from internal service')
            if not data.get('ok'):
                error = data.get('error') or {}
                fail(error.get('code', 'SERVICE_ERROR'), error.get('message', 'Service rejected command'))
            return from_wire(data['result'])
        except httpx.TimeoutException:
            fail('SERVICE_TIMEOUT', f'{SERVICE_NAMES[owner]} service timed out')
        except httpx.RequestError:
            fail('SERVICE_UNAVAILABLE', f'{SERVICE_NAMES[owner]} service is not reachable')


ports = MockRpcPorts()
