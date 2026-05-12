from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.filter(username='admin').first()
if u:
    print(f"FOUND: {u.username}, Staff: {u.is_staff}, Pass OK: {u.check_password('admin123')}")
else:
    print("NOT_FOUND, CREATING...")
    u = User.objects.create_superuser('admin', '+000000000000', 'admin123')
    print("CREATED_SUCCESS")
