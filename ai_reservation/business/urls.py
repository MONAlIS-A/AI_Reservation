from django.urls import path
from . import views

urlpatterns = [
    path("create/", views.create_business, name="create_business"),
    # Browser URL (Page): Uses business_name for clean looks
    path("chat/<str:business_name>/", views.chatbot_page, name="chatbot_page"),
    # AI Receptionist Page (Floating Avatar view)
    path("receptionist/<str:business_name>/", views.receptionist_page, name="receptionist_page"),
    # AI Voice Call Page (Phone-like interface)
    path("call/<str:business_name>/", views.ai_call_page, name="ai_call_page"),
    # Backend API: Uses business_id for robustness against special characters
    path("api/chat/<int:business_id>/", views.chat_api, name="chat_api"),
]