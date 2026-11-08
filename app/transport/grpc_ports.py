"""GraphQL Gateway and Auth client transport: real protobuf/gRPC channels.

Gateway never imports SQL models or domain modules. Connection channels are
reused per service; timeout, credentials and domain errors are handled centrally.
"""
import json
import os
from functools import lru_cache
from datetime import datetime, timezone
from decimal import Decimal

import grpc
from contracts import integration_pb2, integration_pb2_grpc, tutoring_pb2, tutoring_pb2_grpc
from app.core.errors import fail
from app.transport.rpc_codec import to_wire, from_wire
from app.transport.rpc_registry import RPC_METHODS, SERVICE_NAMES
from app.transport import workflows


def _metadata(*, repo=False):
    key = os.getenv('RPC_SHARED_KEY', '')
    if not key:
        fail('CONFIGURATION_ERROR', 'Missing RPC_SHARED_KEY')
    result = [('x-rpc-secret', key)]
    if repo:
        repo_key = os.getenv('AUTH_REPOSITORY_KEY', '')
        if not repo_key:
            fail('CONFIGURATION_ERROR', 'Missing AUTH_REPOSITORY_KEY')
        result.append(('x-auth-repository-key', repo_key))
    return tuple(result)


@lru_cache(maxsize=7)
def channel_for(owner):
    return grpc.insecure_channel(SERVICE_NAMES[owner] + ':50051',
                                 options=(('grpc.enable_retries', 0),))


def _call_with_errors(func, owner, method):
    try:
        return func()
    except grpc.RpcError as exc:
        status = exc.code()
        if status == grpc.StatusCode.DEADLINE_EXCEEDED:
            fail('SERVICE_TIMEOUT', f'{SERVICE_NAMES[owner]} gRPC timeout')
        if status in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.INTERNAL, grpc.StatusCode.RESOURCE_EXHAUSTED):
            fail('SERVICE_UNAVAILABLE', f'{SERVICE_NAMES[owner]} gRPC unavailable')
        if status in (grpc.StatusCode.UNAUTHENTICATED, grpc.StatusCode.PERMISSION_DENIED):
            fail('SERVICE_UNAVAILABLE', 'Internal gRPC authentication failed')
        if status == grpc.StatusCode.INVALID_ARGUMENT:
            fail('BAD_USER_INPUT', 'Invalid gRPC request')
        fail('SERVICE_ERROR', f'{method}: gRPC {status.name}')


def rpc(owner, method, *args, repo=False, **kwargs):
    if RPC_METHODS.get(method, (None,))[0] != owner:
        fail('FORBIDDEN', 'Invalid internal RPC ownership')
    request = integration_pb2.InvokeRequest(
        args_json=json.dumps(to_wire(list(args)), ensure_ascii=False, separators=(',', ':')).encode('utf-8'),
        kwargs_json=json.dumps(to_wire(kwargs), ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    stub = integration_pb2_grpc.InternalOperationsStub(channel_for(owner))
    answer = _call_with_errors(lambda: getattr(stub, method)(request, metadata=_metadata(repo=repo), timeout=12), owner, method)
    if not answer.ok:
        fail(answer.error_code or 'BUSINESS_ERROR', answer.error_message or 'Business operation failed')
    return from_wire(json.loads(answer.result_json.decode('utf-8')))


def typed_offer(teacher_id, subject_id):
    stub = tutoring_pb2_grpc.CatalogStub(channel_for('t'))
    try:
        response = stub.GetTeachingOffer(tutoring_pb2.GetTeachingOfferRequest(
            teacher_id=teacher_id, subject_id=subject_id), metadata=_metadata(), timeout=8)
    except grpc.RpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            return None
        return _call_with_errors(lambda: (_ for _ in ()).throw(exc), 't', 'GetTeachingOffer')
    return {'teacher_id': response.teacher_id, 'subject_id': response.subject_id,
            'price': Decimal(response.price.amount), 'currency': response.price.currency}


def typed_rating(teacher_id):
    stub = tutoring_pb2_grpc.ReputationStub(channel_for('r'))
    try:
        response = stub.GetRating(tutoring_pb2.GetRatingRequest(teacher_id=teacher_id),
                                  metadata=_metadata(), timeout=8)
    except grpc.RpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            return None
        return _call_with_errors(lambda: (_ for _ in ()).throw(exc), 'r', 'GetRating')
    at = response.result.updated_at.ToDatetime(tzinfo=timezone.utc) if response.result.HasField('updated_at') else None
    return {'teacherId': response.result.teacher_id, 'average': Decimal(response.result.average),
            'reviewCount': response.result.review_count, 'version': response.result.version,
            'updatedAt': at}


class GrpcPorts:
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
        if method == 'GetTeachingOffer':
            return typed_offer
        if method == 'GetRating':
            return typed_rating
        owner = RPC_METHODS[method][0]
        return lambda *args, **kwargs: rpc(owner, method, *args, **kwargs)


ports = GrpcPorts()
