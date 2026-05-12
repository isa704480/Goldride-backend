from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# Goldride Branded API Documentation view
schema_view = get_schema_view(
    openapi.Info(
        title="Goldride",
        default_version='v1.0',
        description="Official Command Center API for Goldride Premium Mobility.",
        contact=openapi.Contact(email="dev@goldride.uz"),
        license=openapi.License(name="Proprietary"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    return Response({"status": "healthy"})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health_check, name='health-check'),
    path('api/auth/', include('accounts.urls')),
    path('api/rides/', include('rides.urls')),
    path('api/pricing/', include('pricing.urls')),
    
    # Branded API Documentation (Swagger & ReDoc)
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
