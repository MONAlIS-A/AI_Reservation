from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    BusinessViewSet, 
    BusinessEmbeddingViewSet, 
    AppointmentViewSet, 
    GlobalChatAPIView, 
    ChatAPIView,
    CreateBusinessAPIView,
    BusinessDetailByNameAPIView
)

router = DefaultRouter()
router.register(r'businesses', BusinessViewSet)
router.register(r'embeddings', BusinessEmbeddingViewSet)
router.register(r'appointments', AppointmentViewSet)

urlpatterns = [
    # Router endpoints (Generic CRUD)
    path('v1/', include(router.urls)),
    
    # Custom endpoints that match your existing structure (But now as DRF APIs)
    path("create/", CreateBusinessAPIView.as_view(), name="api_create_business"),# admin create 
    path("global-chat/", GlobalChatAPIView.as_view(), name="api_global_chat_api"), # font desk chatbot 
    
    # Backend Chat API (MUST be above str paths to catch integer IDs first)
    path("chat/<int:business_id>/", ChatAPIView.as_view(), name="api_chat_api"),

    # These return Business data (JSON) instead of rendering HTML pages
    path("chat/<str:business_name>/", BusinessDetailByNameAPIView.as_view(), name="api_chatbot_data"),# business chatbot
    path("receptionist/<str:business_name>/", BusinessDetailByNameAPIView.as_view(), name="api_receptionist_data"),
    path("call/<str:business_name>/", BusinessDetailByNameAPIView.as_view(), name="api_call_data"),
]
