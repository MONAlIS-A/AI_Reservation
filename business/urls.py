from django.urls import path
from . import views

urlpatterns = [
    path("create/", views.create_chatbot, name="create_chatbot"),
    # Dashboard / Global search
    path("", views.global_chat_page, name="global_chat_page"),
    path("api/global-chat/", views.global_chat_api, name="global_chat_api"),
    
    # Browser URL (Page): Uses business_name for clean looks
    path("chat/<str:business_name>/", views.chatbot_page, name="chatbot_page"),
    # AI Receptionist Page (Floating Avatar view)
    path("receptionist/<str:business_name>/", views.receptionist_page, name="receptionist_page"),
    # AI Voice Call Page (Phone-like interface)
    path("call/<str:business_name>/", views.ai_call_page, name="ai_call_page"),
    # Backend API: Uses business_id for robustness against special characters
    path("api/chat/<int:business_id>/", views.chat_api, name="chat_api"),
    path("voice-receptionist/", views.voice_receptionist_home, name="voice_receptionist_home"),
    path("api/realtime-session/", views.realtime_session_view, name="realtime_session"),
    path("api/check-availability/", views.check_availability_api, name="check_availability_api"),
    path("api/create-booking/", views.create_booking_api, name="create_booking_api"),
    path("inquiry/<int:business_id>/", views.booking_inquiry_view, name="booking_inquiry"),
]