"""
URL configuration for ai_reservation project.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="AI Reservation API",
        default_version='v1',
        description="Multi-Tenant AI Reservation & Discovery System API.\n\n"
                    "This API powers a global AI discovery assistant that helps users find businesses, "
                    "explore services, and make reservations through dedicated AI receptionists.",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="support@ai-reservation.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Swagger UI & API Docs
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('swagger.json', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger.yaml', schema_view.without_ui(cache_timeout=0), name='schema-yaml'),

    # API endpoints
    path('api/', include('business.api_urls')),
    path('', include("business.urls")),
]
