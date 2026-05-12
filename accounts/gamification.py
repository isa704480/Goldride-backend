from django.utils import timezone
from .models import DriverGoal, GoalProgress


def update_driver_goals(driver):
    """
    Updates progress for all active goals for a driver.
    Called whenever a ride is completed.
    """
    today = timezone.now().date()
    active_goals = DriverGoal.objects.filter(is_active=True)

    for goal in active_goals:
        # For daily goals, we filter by today's date
        # For monthly, we would need to filter by month (simplified to daily here)
        progress, created = GoalProgress.objects.get_or_create(
            driver=driver,
            goal=goal,
            date=today
        )

        if not progress.is_completed:
            progress.current_count += 1
            
            if progress.current_count >= goal.target_rides:
                progress.is_completed = True
                # Award reward
                driver.total_earnings += goal.reward_amount
                driver.save(update_fields=['total_earnings'])
            
            progress.save()

    # Also update total rides count for badges
    driver.total_rides += 1
    driver.save(update_fields=['total_rides'])
    
    # Simple Badge Logic:
    # 10 rides = "Yo'l ustasi"
    # 50 rides = "Professionallar clubi"
    # This could be expanded later
