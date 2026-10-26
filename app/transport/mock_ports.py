"""Local, replaceable adapters implementing the read-side RPC surface of lab 2.

No network requests and no gRPC yet (lab 3 requirement). The gateway receives
only this transport facade, never another service's SQLAlchemy engine.
"""
from app.services import accounts, catalog, learning, payments, reputation, notifications, analytics
from app.services import accounts_write, catalog_write, learning_write, payments_write, reputation_write, notifications_write, analytics_write
from app.transport import workflows


class MockRpcPorts:
    """The method names intentionally match the RPC verbs in tutoring.proto."""

    # Lab 4 write operations exposed through the mock transport facade.
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

    # Local service-owned methods. Transport never accesses a foreign repository.
    RegisterUserLocal = staticmethod(accounts_write.register_user)
    LoginLocal = staticmethod(accounts_write.login_user)
    SetUserStatusLocal = staticmethod(accounts_write.set_user_status)
    UpdateTeacherProfileLocal = staticmethod(catalog_write.update_teacher_profile)
    ManageSubjectLocal = staticmethod(catalog_write.manage_subject)
    GetTeachingOffer = staticmethod(catalog_write.teaching_offer)
    UpdateRatingProjection = staticmethod(catalog_write.update_rating_projection)
    UpdatePopularity = staticmethod(catalog_write.update_popularity_projection)
    SetAvailabilityLocal = staticmethod(learning_write.set_availability)
    BookLessonLocal = staticmethod(learning_write.book_lesson)
    ChangeLessonLocal = staticmethod(learning_write.change_lesson)
    GetLessonSnapshot = staticmethod(learning_write.lesson_snapshot)
    GetBookingSnapshot = staticmethod(learning_write.booking_snapshot)
    ApplyPaymentToBooking = staticmethod(learning_write.apply_payment)
    RegisterPaymentLocal = staticmethod(payments_write.register_payment)
    AddReviewLocal = staticmethod(reputation_write.add_review)
    MarkNotificationReadLocal = staticmethod(notifications_write.mark_notification_read)
    SendNotification = staticmethod(notifications_write.notify)
    ProjectLesson = staticmethod(analytics_write.project_lesson)
    ProjectPayment = staticmethod(analytics_write.project_payment)
    ProjectReview = staticmethod(analytics_write.project_review)
    RecordAuthentication = staticmethod(analytics_write.project_auth)

    # Accounts
    ValidateSession = staticmethod(accounts.validate_session)
    GetMe = staticmethod(accounts.get_user)
    ListUsers = staticmethod(accounts.list_users)
    GetStudent = staticmethod(accounts.get_student)

    # Catalog
    SearchTeachers = staticmethod(catalog.search_teachers)
    GetTeacher = staticmethod(catalog.get_teacher)
    ListSubjects = staticmethod(catalog.list_subjects)
    GetTeacherSubjects = staticmethod(catalog.teacher_subjects)
    GetTeacherMetrics = staticmethod(catalog.metrics)

    # Learning
    ListAvailableSlots = staticmethod(learning.available_slots)
    GetMySchedule = staticmethod(learning.my_schedule)
    ListLessons = staticmethod(learning.lessons_for_actor)
    ListMyBookings = staticmethod(learning.my_bookings)
    GetSlot = staticmethod(learning.get_slot)
    GetLesson = staticmethod(learning.get_lesson)

    # Payments, Reputation, Notifications, Analytics
    ListMyPayments = staticmethod(payments.my_payments)
    ListReviews = staticmethod(reputation.list_reviews)
    GetRating = staticmethod(reputation.get_rating)
    ListNotifications = staticmethod(notifications.list_notifications)
    GetPlatformAnalytics = staticmethod(analytics.platform_analytics)


ports = MockRpcPorts()
