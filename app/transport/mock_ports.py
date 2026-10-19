"""Local, replaceable adapters implementing the read-side RPC surface of lab 2.

No network requests and no gRPC yet (lab 3 requirement). The gateway receives
only this transport facade, never another service's SQLAlchemy engine.
"""
from app.services import accounts, catalog, learning, payments, reputation, notifications, analytics


class MockRpcPorts:
    """The method names intentionally match the RPC verbs in tutoring.proto."""

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
