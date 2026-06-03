from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="Goldride API",
        default_version='v1',
        description="""
## Goldride — Premium Taksi Agregator

### Autentifikatsiya
Barcha himoyalangan endpointlar uchun **Bearer token** kerak:
```
Authorization: Bearer <access_token>
```

### Token olish
1. `POST /api/auth/send-otp/` — OTP yuborish
2. `POST /api/auth/verify-otp/` — OTP tasdiqlash → access/refresh token

### Asosiy bo'limlar
- **Auth** — OTP, Telegram, Google login
- **Rides** — Buyurtma yaratish, haydovchi boshqaruvi
- **Accounts** — Profil, hamyon, maqsadlar
- **Pricing** — Narx hisoblash
        """,
        contact=openapi.Contact(email="dev@goldride.uz"),
        license=openapi.License(name="Proprietary"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    authentication_classes=[],
)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    return Response({"status": "healthy", "version": "1.0"})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health-check'),
    path('api/auth/', include('accounts.urls')),
    path('api/rides/', include('rides.urls')),
    path('api/pricing/', include('pricing.urls')),

    # API Docs — production'da ham ishlaydi (drf_yasg static fayllarni o'zi serve qiladi)
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('docs/json/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
