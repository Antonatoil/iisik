"""Real cross-service business workflows via synchronous gRPC.

Local commits create transactional outbox events; Kafka consumers update
read models and notifications asynchronously, not via Gateway mock calls.
"""
from app.core.errors import require_role, fail
from graphql import GraphQLError
from app.resilience.telemetry import emit


def business_condition(test, code, message):
    if not test:
        fail(code, message)


def _ports():
    from app.transport.grpc_ports import ports
    return ports


def register(arg):
    from app.transport.auth_client import register as auth_register
    return auth_register(arg)


def login(arg):
    from app.transport.auth_client import login as auth_login
    return auth_login(arg)


def update_teacher_profile(actor, arg):
    require_role(actor,'TEACHER')
    return _ports().UpdateTeacherProfileLocal(actor,arg)


def set_availability(actor,arg):
    require_role(actor,'TEACHER')
    business_condition(_ports().GetTeachingOffer(actor['id'],arg['subjectId']) is not None,
        'INVALID_OFFER','Teacher profile must offer the chosen active subject')
    return _ports().SetAvailabilityLocal(actor,arg)


def book_lesson(actor,arg):
    require_role(actor,'STUDENT')
    offer=_ports().GetTeachingOffer(arg['teacherId'],arg['subjectId'])
    return _ports().BookLessonLocal(actor,arg,offer)
    # Learning saves LessonBooked in its outbox in the same DB-L transaction.
    # Analytics and Notifications consume it through Kafka.


def change_lesson(actor,arg,action):
    require_role(actor,'STUDENT','TEACHER')
    return _ports().ChangeLessonLocal(actor,arg,action)


def register_payment(actor,arg):
    require_role(actor,'STUDENT')
    booking=_ports().GetBookingSnapshot(arg['bookingId'])
    business_condition(booking is not None and booking['student_id']==actor['id'],
                       'NOT_FOUND','Booking not found')
    business_condition(booking['booking_status']=='ACTIVE','INVALID_STATE','Booking is not active')
    business_condition(booking['payment_state']!='PAID' or booking['payment_operation_id']==arg['operationId'],
                       'ALREADY_PAID','This booking is already paid')
    result=_ports().RegisterPaymentLocal(actor,arg,booking)
    if result['status']=='COMPLETED':
        # Fast synchronous availability for subsequent StartLesson commands;
        # Kafka PaymentCompleted consumer independently retries the same
        # idempotent update and populates analytics/notifications asynchronously.
        try:
            _ports().ApplyPaymentToBooking(arg['bookingId'],arg['operationId'])
        except GraphQLError as exc:
            code=(exc.extensions or {}).get('code')
            if code not in ('SERVICE_TIMEOUT','SERVICE_UNAVAILABLE'):
                raise
            # Payment has already committed with PaymentCompleted in DB-P outbox.
            # Do not report it as failed or retry the mutation blindly.
            # Learning's Kafka consumer will reconcile the booking when it recovers.
            emit('payment_sync_deferred',level='warning',service='payments',
                 operation_id=arg['operationId'],booking_id=arg['bookingId'],error_code=code)
    return result


def add_review(actor,arg):
    require_role(actor,'STUDENT')
    booking=_ports().GetBookingSnapshot(arg['bookingId'])
    return _ports().AddReviewLocal(actor,arg,booking)


def mark_notification_read(actor,arg):
    require_role(actor,'STUDENT','TEACHER','ADMIN')
    return _ports().MarkNotificationReadLocal(actor,arg)


def set_user_status(actor,arg):
    require_role(actor,'ADMIN')
    result=_ports().SetUserStatusLocal(actor,arg)
    if result['status']=='BLOCKED':
        from app.transport.auth_client import revoke_user
        revoke_user(result['id'])
    return result


def manage_subject(actor,arg):
    require_role(actor,'ADMIN')
    return _ports().ManageSubjectLocal(actor,arg)
