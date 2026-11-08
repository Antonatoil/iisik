"""Allowlist of domain RPC operations assigned to owning gRPC services.

The names preserve the existing GraphQL domain adapter API. Modules load
only inside the owning service process, never inside GraphQL Gateway.
"""

RPC_METHODS = {
    # Accounts / DB-A
    'ValidateSession': ('a', 'accounts.validate_session'),  # retained for Lab-4 compatibility only
    'ReadCredentialForAuth': ('a', 'accounts.get_credential_for_auth'),
    'GetMe': ('a', 'accounts.get_user'),
    'ListUsers': ('a', 'accounts.list_users'),
    'GetStudent': ('a', 'accounts.get_student'),
    'RegisterUserLocal': ('a', 'accounts_write.register_user'),
    'LoginLocal': ('a', 'accounts_write.login_user'),
    'SetUserStatusLocal': ('a', 'accounts_write.set_user_status'),
    # Catalog / DB-T
    'SearchTeachers': ('t', 'catalog.search_teachers'),
    'GetTeacher': ('t', 'catalog.get_teacher'),
    'ListSubjects': ('t', 'catalog.list_subjects'),
    'GetTeacherSubjects': ('t', 'catalog.teacher_subjects'),
    'GetTeacherMetrics': ('t', 'catalog.metrics'),
    'UpdateTeacherProfileLocal': ('t', 'catalog_write.update_teacher_profile'),
    'ManageSubjectLocal': ('t', 'catalog_write.manage_subject'),
    'GetTeachingOffer': ('t', 'catalog_write.teaching_offer'),
    'UpdateRatingProjection': ('t', 'catalog_write.update_rating_projection'),
    'UpdatePopularity': ('t', 'catalog_write.update_popularity_projection'),
    # Learning / DB-L
    'ListAvailableSlots': ('l', 'learning.available_slots'),
    'GetMySchedule': ('l', 'learning.my_schedule'),
    'ListLessons': ('l', 'learning.lessons_for_actor'),
    'ListMyBookings': ('l', 'learning.my_bookings'),
    'GetSlot': ('l', 'learning.get_slot'),
    'GetLesson': ('l', 'learning.get_lesson'),
    'SetAvailabilityLocal': ('l', 'learning_write.set_availability'),
    'BookLessonLocal': ('l', 'learning_write.book_lesson'),
    'ChangeLessonLocal': ('l', 'learning_write.change_lesson'),
    'GetLessonSnapshot': ('l', 'learning_write.lesson_snapshot'),
    'GetBookingSnapshot': ('l', 'learning_write.booking_snapshot'),
    'ApplyPaymentToBooking': ('l', 'learning_write.apply_payment'),
    # Payments / DB-P
    'ListMyPayments': ('p', 'payments.my_payments'),
    'RegisterPaymentLocal': ('p', 'payments_write.register_payment'),
    # Reputation / DB-R
    'ListReviews': ('r', 'reputation.list_reviews'),
    'GetRating': ('r', 'reputation.get_rating'),
    'AddReviewLocal': ('r', 'reputation_write.add_review'),
    # Notifications / DB-N
    'ListNotifications': ('n', 'notifications.list_notifications'),
    'MarkNotificationReadLocal': ('n', 'notifications_write.mark_notification_read'),
    'SendNotification': ('n', 'notifications_write.notify'),
    # Analytics / DB-X
    'GetPlatformAnalytics': ('x', 'analytics.platform_analytics'),
    'ProjectLesson': ('x', 'analytics_write.project_lesson'),
    'ProjectPayment': ('x', 'analytics_write.project_payment'),
    'ProjectReview': ('x', 'analytics_write.project_review'),
    'RecordAuthentication': ('x', 'analytics_write.project_auth'),
}

SERVICE_NAMES = {
    'a': 'accounts', 't': 'catalog', 'l': 'learning', 'p': 'payments',
    'r': 'reputation', 'n': 'notifications', 'x': 'analytics',
}

assert len(RPC_METHODS) == len(set(RPC_METHODS)), 'Duplicate RPC method'
