"""Local mock workflow coordinator. Only calls ports, never opens another service's DB.
No true distributed transaction: follow-up projection/notification delivery is synchronous
in this educational version and must be made durable by Kafka/outbox in later labs.
"""
from app.core.commands import business_condition
from app.core.validation import valid_id
from app.core.errors import require_role


def _ports():
    from app.transport.mock_ports import ports
    return ports


def register(arg):
    return _ports().RegisterUserLocal(arg)


def login(arg):
    result=_ports().LoginLocal(arg)
    _ports().RecordAuthentication(result['user'])
    return result


def update_teacher_profile(actor,arg):
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
    result=_ports().BookLessonLocal(actor,arg,offer)
    _ports().ProjectLesson(_ports().GetLessonSnapshot(result['lesson_id']))
    _ports().SendNotification(actor['id'],'LessonBooked',result['lesson_id'],'Вы записаны на занятие',arg['operationId'])
    return result


def change_lesson(actor,arg,action):
    require_role(actor,'STUDENT','TEACHER')
    result=_ports().ChangeLessonLocal(actor,arg,action)
    popularity = None
    snapshot=_ports().GetLessonSnapshot(arg['lessonId'])
    if action in ('cancelLesson','rescheduleLesson','completeLesson'):
        popularity = _ports().ProjectLesson(snapshot)
    if action=='completeLesson' and popularity:
        _ports().UpdatePopularity(snapshot['teacher_id'],popularity['completed_count'],popularity['version'])
    if action in ('cancelLesson','rescheduleLesson','completeLesson'):
        who=snapshot['student_id'] if actor['role']=='TEACHER' else snapshot['teacher_id']
        _ports().SendNotification(who,action,arg['lessonId'],f'Изменено занятие: {action}',arg['operationId'])
    return result


def register_payment(actor,arg):
    require_role(actor,'STUDENT')
    booking=_ports().GetBookingSnapshot(arg['bookingId'])
    business_condition(booking is not None and booking['student_id']==actor['id'],'NOT_FOUND','Booking not found')
    business_condition(booking['booking_status']=='ACTIVE','INVALID_STATE','Booking is not active')
    business_condition(booking['payment_state']!='PAID' or booking['payment_operation_id']==arg['operationId'],
         'ALREADY_PAID','This booking is already paid')
    result=_ports().RegisterPaymentLocal(actor,arg,booking)
    if result['status']=='COMPLETED':
        _ports().ApplyPaymentToBooking(arg['bookingId'],arg['operationId'])
        _ports().ProjectPayment(result,booking)
        _ports().SendNotification(actor['id'],'PaymentCompleted',arg['bookingId'],'Оплата занятия подтверждена (демо)',arg['operationId'])
    return result


def add_review(actor,arg):
    require_role(actor,'STUDENT')
    booking=_ports().GetBookingSnapshot(arg['bookingId'])
    result=_ports().AddReviewLocal(actor,arg,booking)
    rating=_ports().GetRating(booking['teacher_id'])
    _ports().ProjectReview(result,booking['teacher_id'],rating)
    _ports().UpdateRatingProjection(booking['teacher_id'],rating['average'],rating['reviewCount'],rating['version'],rating['updatedAt'])
    _ports().SendNotification(booking['teacher_id'],'ReviewCreated',result['id'],'Оставлен новый отзыв',arg['operationId'])
    return result


def mark_notification_read(actor,arg):
    require_role(actor,'STUDENT','TEACHER','ADMIN')
    return _ports().MarkNotificationReadLocal(actor,arg)


def set_user_status(actor,arg):
    require_role(actor,'ADMIN')
    return _ports().SetUserStatusLocal(actor,arg)


def manage_subject(actor,arg):
    require_role(actor,'ADMIN')
    return _ports().ManageSubjectLocal(actor,arg)
