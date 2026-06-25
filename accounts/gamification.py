def update_driver_goals(driver, ride=None):
    """
    DEPRECATED → accounts.cashback.check_and_complete_driver_goal.

    Eski versiya mavjud bo'lmagan model maydonlariga (goal.target_rides,
    GoalProgress.date, is_completed) murojaat qilib, chaqirilsa crash berardi.
    Endi to'g'ri maqsad logikasi cashback modulida. Bu funksiya faqat
    moslik uchun qoldirilgan va o'sha logikaga yo'naltiradi.
    """
    from accounts.cashback import check_and_complete_driver_goal
    if ride is not None:
        check_and_complete_driver_goal(driver, ride)
