"""Real internal gRPC server, with explicit ownership and bounded RPC payloads.

Typed Lab-2 methods are exposed for the frequently used Catalog offer and
Reputation rating calls. All additional Lab-4 internal operations use the
versioned Integration protobuf extension to preserve their Python API.
"""
import hmac
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from importlib import import_module

import grpc
from graphql import GraphQLError
from google.protobuf.timestamp_pb2 import Timestamp
from contracts import integration_pb2, integration_pb2_grpc, tutoring_pb2, tutoring_pb2_grpc
from app.transport.rpc_codec import from_wire, to_wire
from app.transport.rpc_registry import RPC_METHODS, SERVICE_NAMES

log = logging.getLogger(__name__)


def check_request(context, *, credentials=False):
    meta = dict(context.invocation_metadata())
    expected = os.getenv('RPC_SHARED_KEY', '')
    supplied = meta.get('x-rpc-secret', '')
    if not expected or not hmac.compare_digest(supplied, expected):
        context.abort(grpc.StatusCode.UNAUTHENTICATED, 'Internal gRPC credentials rejected')
    if credentials:
        expected_repo = os.getenv('AUTH_REPOSITORY_KEY', '')
        repo_key = meta.get('x-auth-repository-key', '')
        if not expected_repo or not hmac.compare_digest(repo_key, expected_repo):
            context.abort(grpc.StatusCode.PERMISSION_DENIED, 'Credential repository access denied')


def _handlers(owner):
    result = {}
    for method, (method_owner, target) in RPC_METHODS.items():
        if method_owner != owner:
            continue
        module, function = target.rsplit('.', 1)
        result[method] = getattr(import_module('app.services.' + module), function)
    return result


class Operations(integration_pb2_grpc.InternalOperationsServicer):
    def __init__(self, owner):
        self.owner = owner
        self.handlers = _handlers(owner)

    def Check(self, request, context):
        check_request(context)
        return integration_pb2.HealthReply(service=SERVICE_NAMES[self.owner], ready=True)

    def __getattr__(self, method):
        # Each generated protobuf RPC has a concrete named server handler.
        if method not in RPC_METHODS:
            raise AttributeError(method)
        return lambda request, context: self._invoke_named(method, request, context)

    def _invoke_named(self, method, request, context):
        check_request(context, credentials=method == 'ReadCredentialForAuth')
        handler = self.handlers.get(method)
        if handler is None:
            context.abort(grpc.StatusCode.NOT_FOUND, 'Method not provided by this service')
        if len(request.args_json) > 1024 * 1024 or len(request.kwargs_json) > 1024 * 1024:
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, 'RPC payload too large')
        try:
            args = from_wire(json.loads(request.args_json.decode('utf-8')))
            kwargs = from_wire(json.loads(request.kwargs_json.decode('utf-8')))
            if not isinstance(args, list) or not isinstance(kwargs, dict):
                raise ValueError('Invalid request structure')
        except (UnicodeDecodeError, ValueError, TypeError, KeyError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'Invalid gRPC request payload')
        try:
            result = handler(*args, **kwargs)
            return integration_pb2.InvokeReply(ok=True, result_json=json.dumps(to_wire(result),
                    ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        except GraphQLError as error:
            return integration_pb2.InvokeReply(ok=False,
                error_code=(error.extensions or {}).get('code', 'BUSINESS_ERROR'),
                error_message=error.message)
        except (ValueError, KeyError, TypeError):
            return integration_pb2.InvokeReply(ok=False, error_code='BAD_USER_INPUT',
                                               error_message='Invalid command data')
        except Exception:
            log.exception('gRPC error: %s/%s', self.owner, method)
            context.abort(grpc.StatusCode.INTERNAL, 'Internal service error')


# grpc_tools generates no-op UNIMPLEMENTED methods on its base servicer.
# Attach a concrete handler for every named protobuf RPC, overriding those
# inherited methods. __getattr__ alone is NOT sufficient in Python.
def _bind_rpc(method):
    def invoke(self, request, context):
        return self._invoke_named(method, request, context)
    invoke.__name__ = method
    return invoke

for _method in RPC_METHODS:
    setattr(Operations, _method, _bind_rpc(_method))


class CatalogTyped(tutoring_pb2_grpc.CatalogServicer):
    def GetTeachingOffer(self, request, context):
        check_request(context)
        from app.services.catalog_write import teaching_offer
        try:
            offer = teaching_offer(request.teacher_id, request.subject_id)
        except (ValueError, GraphQLError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'Invalid teacher or subject')
        if not offer:
            context.abort(grpc.StatusCode.NOT_FOUND, 'No active teaching offer')
        return tutoring_pb2.TeachingOffer(
            teacher_id=offer['teacher_id'], teacher_user_id=offer['teacher_id'],
            subject_id=offer['subject_id'],
            price=tutoring_pb2.Money(amount=str(offer['price']), currency=offer['currency']))


class ReputationTyped(tutoring_pb2_grpc.ReputationServicer):
    def GetRating(self, request, context):
        check_request(context)
        from app.services.reputation import get_rating
        try:
            rating = get_rating(request.teacher_id)
        except (ValueError, GraphQLError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'Invalid teacher')
        if rating is None:
            context.abort(grpc.StatusCode.NOT_FOUND, 'No rating')
        result = tutoring_pb2.Rating(
            teacher_id=rating['teacherId'], average=str(rating['average']),
            review_count=rating['reviewCount'], version=rating['version'])
        if rating['updatedAt']:
            at = rating['updatedAt']
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            result.updated_at.FromDatetime(at)
        return tutoring_pb2.GetRatingResponse(result=result)


def start(owner):
    executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix=owner+'-grpc')
    server = grpc.server(executor,
                         options=[('grpc.max_receive_message_length', 1024*1024),
                                  ('grpc.max_send_message_length', 1024*1024),
                                  ('grpc.keepalive_time_ms', 30000)])
    integration_pb2_grpc.add_InternalOperationsServicer_to_server(Operations(owner), server)
    if owner == 't':
        tutoring_pb2_grpc.add_CatalogServicer_to_server(CatalogTyped(), server)
    if owner == 'r':
        tutoring_pb2_grpc.add_ReputationServicer_to_server(ReputationTyped(), server)
    server.add_insecure_port('0.0.0.0:50051')
    server.start()
    log.info('gRPC ready: %s:50051', SERVICE_NAMES[owner])
    return server
