from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .forms import BusinessForm
from .models import Business, BusinessEmbedding, BusinessService, ChatHistory
from .rag import build_pipeline_and_get_db, aget_rag_answer_with_agent, aget_global_rag_answer
from asgiref.sync import async_to_sync
import httpx
import os
import json
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi


from external_db_handler import check_availability as db_check_availability, create_booking_ext as db_create_booking


# -------------------------------
# Realtime Tools API
# -------------------------------
@swagger_auto_schema(
    method='post',
    operation_description="Check service availability for a specific time slot.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['service', 'time'],
        properties={
            'service': openapi.Schema(type=openapi.TYPE_STRING, description='Service name'),
            'time': openapi.Schema(type=openapi.TYPE_STRING, description='Desired time (YYYY-MM-DD HH:MM)')
        }
    ),
    responses={200: openapi.Response(description="Availability results")},
    tags=['Realtime Tools']
)
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def check_availability_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        service = data.get('service')
        time = data.get('time')
        result = db_check_availability(service, time)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@swagger_auto_schema(
    method='post',
    operation_description="Create a new booking in the system.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['service', 'time', 'name', 'phone', 'email'],
        properties={
            'service': openapi.Schema(type=openapi.TYPE_STRING),
            'time': openapi.Schema(type=openapi.TYPE_STRING),
            'name': openapi.Schema(type=openapi.TYPE_STRING),
            'phone': openapi.Schema(type=openapi.TYPE_STRING),
            'email': openapi.Schema(type=openapi.TYPE_STRING),
            'notes': openapi.Schema(type=openapi.TYPE_STRING),
        }
    ),
    responses={200: openapi.Response(description="Booking confirmation")},
    tags=['Realtime Tools']
)
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def create_booking_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        service_name = data.get('service')
        time_str = data.get('time')
        name = data.get('name')
        phone = data.get('phone')
        email = data.get('email', '')
        notes = data.get('notes', '')

        # 1. Create in external DB
        result = db_create_booking(
            service_name,
            time_str,
            name,
            phone,
            notes
        )

        # 2. Also save to local Appointment model for status tracking and payment
        if result.get('status') == 'success':
            from .models import Appointment, Business
            import datetime
            try:
                # Try to find business related to the service
                service_obj = BusinessService.objects.filter(name__iexact=service_name).first()
                business = service_obj.business if service_obj else Business.objects.first()
                
                target_time = datetime.datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                # Default duration 60 mins if not found
                duration = service_obj.duration_minutes if service_obj and service_obj.duration_minutes else 60
                end_time = target_time + datetime.timedelta(minutes=duration)

                Appointment.objects.create(
                    business=business,
                    customer_name=name,
                    customer_email=email,
                    customer_phone=phone,
                    service_name=service_name,
                    start_time=target_time,
                    end_time=end_time,
                    payment_status='pending'
                )
            except Exception as e:
                print(f"Failed to save local appointment: {e}")

        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# -------------------------------
# Customer Service / Inquiry
# -------------------------------
@swagger_auto_schema(
    method='get',
    operation_description="Page - Booking Inquiry. Shows services based on business slug/ID.",
    manual_parameters=[
        openapi.Parameter('business_id', openapi.IN_PATH, description="ID or UUID", type=openapi.TYPE_STRING),
    ],
    tags=['Pages']
)
@api_view(['GET'])
@permission_classes([AllowAny])
def booking_inquiry_view(request, business_id):
    """Page for selecting a service and starting a voice call."""
    # Try ID first, then fallback to external_uuid
    try:
        if str(business_id).isdigit():
            business = Business.objects.filter(id=int(business_id)).first()
        else:
            business = Business.objects.filter(external_uuid=business_id).first()
            
        if not business:
            raise Business.DoesNotExist
    except:
        from django.http import HttpResponse
        if request.accepted_renderer.format == 'html' or 'text/html' in request.META.get('HTTP_ACCEPT', ''):
            return HttpResponse(f"Error: Business with ID/UUID {business_id} was not found. Please check your URL.", status=200)
        return JsonResponse({'error': 'Business not found'}, status=404)
    
    # Filter services for this business
    services = BusinessService.objects.filter(business=business)
    
    if request.accepted_renderer.format == 'html' or 'text/html' in request.META.get('HTTP_ACCEPT', ''):
        return render(request, 'business/booking_inquiry.html', {
            'business': business,
            'services': services
        })
        
    return JsonResponse({
        'business': business.name,
        'services': list(services.values('id', 'name', 'price', 'description'))
    })


# -------------------------------
# Realtime Session (WebRTC)
# -------------------------------
@swagger_auto_schema(
    method='post',
    operation_description="Fetch an ephemeral session token from OpenAI for client-side WebRTC connection. Useful for Voice AI interaction.",
    responses={200: openapi.Response(description="OpenAI Session data")},
    tags=['Realtime Tools']
)
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def realtime_session_view(request):
    """
    Fetch an ephemeral session token from OpenAI for client-side WebRTC connection.
    Bypasses Render's WebSocket limitations by connecting directly from browser.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    from external_db_handler import get_openai_api_key
    api_key = get_openai_api_key()
    if not api_key:
        return JsonResponse({'error': 'OPENAI_API_KEY not configured on server'}, status=500)

    try:
        # 1. Fetch available services from external DB for the prompt
        from external_db_handler import get_connection
        service_names = []
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                # Fetch distinct active service names
                cur.execute("SELECT DISTINCT service_name FROM core.services WHERE is_active = true")
                rows = cur.fetchall()
                service_names = [r[0] for r in rows if r[0]]
            conn.close()
            print(f"[VOICE] Found {len(service_names)} services in DB for prompt.")
        except Exception as db_e:
            print(f"[ERROR] Could not fetch services for voice prompt: {db_e}")

    # 2. Request a temporary session from OpenAI with retry
    api_key = get_openai_api_key()
    retry_count = 0
    max_retries = 1
    
    while retry_count <= max_retries:
        try:
            with httpx.Client() as client:
                response = client.post(
                    "https://api.openai.com/v1/realtime/sessions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-realtime-preview-2024-12-17",
                        "voice": "alloy",
                    },
                    timeout=10.0
                )
            
            if response.status_code == 200:
                session_data = response.json()
                session_data['available_services'] = service_names # Pass services to frontend
                return JsonResponse(session_data)
            
            # If auth error and we haven't retried yet
            if response.status_code == 401 and retry_count < max_retries:
                print(f"[RETRY] OpenAI session failed (401). Refreshing API key...")
                api_key = get_openai_api_key(force_refresh=True)
                retry_count += 1
                continue
            
            return JsonResponse({
                'error': f'OpenAI session API failed: {response.status_code}',
                'details': response.text
            }, status=response.status_code)

        except Exception as e:
            if retry_count < max_retries:
                print(f"[RETRY] OpenAI session exception: {e}. Refreshing API key...")
                api_key = get_openai_api_key(force_refresh=True)
                retry_count += 1
                continue
            raise e
        
    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch session: {str(e)}'}, status=500)


# -------------------------------
# Business Creation
# -------------------------------
@swagger_auto_schema(
    method='post',
    operation_description="Create a new chatbot/business and generate embeddings.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['name'],
        properties={
            'name': openapi.Schema(type=openapi.TYPE_STRING),
            'description': openapi.Schema(type=openapi.TYPE_STRING),
            'website_url': openapi.Schema(type=openapi.TYPE_STRING),
        }
    ),
    responses={200: openapi.Response(description="Chatbot created")},
    tags=['Business Management']
)
@api_view(['POST', 'GET'])
@permission_classes([AllowAny])
@csrf_exempt
def create_chatbot(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            # Process the chatbot creation logic here
            name = data.get("name")
            description = data.get("description", "")
            website_url = data.get("website_url", "")

            # Create the business/chatbot in the database
            business = Business.objects.create(
                name=name,
                description=description,
                website_url=website_url
            )

            # Build the RAG pipeline/embeddings
            try:
                build_pipeline_and_get_db(business_id=business.id)
            except Exception as e:
                print(f"Embedding failed: {e}")

            return JsonResponse({
                "message": "Chatbot created successfully",
                "id": business.id,
                "name": business.name
            })
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)


def create_business(request):
    if request.method == 'POST':
        form = BusinessForm(request.POST)
        if form.is_valid():
            business_instance = form.save()
            try:
                build_pipeline_and_get_db(business_id=business_instance.id)
            except Exception as e:
                print(f"Embedding generation failed: {e}")
            return redirect('create_business')
    else:
        form = BusinessForm()

    return render(request, 'business/business_form.html', {'form': form})


# -------------------------------
# Pages
# -------------------------------
@swagger_auto_schema(
    method='get',
    operation_description="Page - Main Chat Interface for a business.",
    responses={200: openapi.Response(description="Business detail data for the chatbot")},
    tags=['Pages']
)
@api_view(['GET'])
@permission_classes([AllowAny])
def chatbot_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    if request.accepted_renderer.format == 'html' or 'text/html' in request.META.get('HTTP_ACCEPT', ''):
        return render(request, 'business/chatbot.html', {'business': business})
    return JsonResponse({
        'name': business.name,
        'description': business.description,
        'website_url': business.website_url,
        'external_uuid': str(business.external_uuid) if business.external_uuid else None
    })


@swagger_auto_schema(
    method='get',
    operation_description="Page - AI Receptionist view (Floating Avatar).",
    responses={200: openapi.Response(description="Business data for receptionist")},
    tags=['Pages']
)
@api_view(['GET'])
@permission_classes([AllowAny])
def receptionist_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    if request.accepted_renderer.format == 'html' or 'text/html' in request.META.get('HTTP_ACCEPT', ''):
        return render(request, 'business/receptionist.html', {'business': business})
    return JsonResponse({
        'name': business.name,
        'id': business.id,
        'external_uuid': str(business.external_uuid)
    })


@swagger_auto_schema(
    method='get',
    operation_description="Page - Voice Call Interface.",
    responses={200: openapi.Response(description="Business details for voice call")},
    tags=['Pages']
)
@api_view(['GET'])
@permission_classes([AllowAny])
def ai_call_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    if request.accepted_renderer.format == 'html' or 'text/html' in request.META.get('HTTP_ACCEPT', ''):
        return render(request, 'business/ai_call.html', {'business': business})
    return JsonResponse({'name': business.name, 'id': business.id})


@swagger_auto_schema(
    method='get',
    operation_description="Page - Voice Receptionist Home.",
    tags=['Pages']
)
@api_view(['GET'])
@permission_classes([AllowAny])
def voice_receptionist_home(request):
    if request.accepted_renderer.format == 'html' or 'text/html' in request.META.get('HTTP_ACCEPT', ''):
        return render(request, 'business/voice_receptionist.html')
    return JsonResponse({'message': 'Voice Receptionist Home API'})

@swagger_auto_schema(
    method='get',
    operation_description="Page - Global Discovery Chat.",
    tags=['Pages']
)
@api_view(['GET'])
@permission_classes([AllowAny])
def global_chat_page(request):
    if request.accepted_renderer.format == 'html' or 'text/html' in request.META.get('HTTP_ACCEPT', ''):
        return render(request, 'business/global_chat.html')
    return JsonResponse({'message': 'Welcome to Global Discovery Assistant'})


from django.db import transaction

from django.db.models import Q

@swagger_auto_schema(
    method='post',
    operation_description="Global Discovery Chat API. Search across all businesses.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['message'],
        properties={
            'message': openapi.Schema(type=openapi.TYPE_STRING),
            'chat_history': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
            'user_id': openapi.Schema(type=openapi.TYPE_STRING),
        }
    ),
    responses={200: openapi.Response(description="AI Answer")},
    tags=['Discovery']
)
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def global_chat_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_query = data.get('message', '').strip() or "Hello!"
            
            # ✅ Client-side History Source
            history = data.get('chat_history', [])

            # ✅ RUN AI RAG (Stateless)
            bot_answer = async_to_sync(aget_global_rag_answer)(
                user_query,
                chat_history=history
            )

            # ✅ Cleanup: Delete records older than 1 hour for this user
            from django.utils import timezone
            from datetime import timedelta
            one_hour_ago = timezone.now() - timedelta(hours=1)
            
            # Backup Log (Stateless AI doesn't strictly need this, but good for logs)
            user_id = data.get('user_id') or request.session.session_key
            with transaction.atomic():
                if user_id:
                    ChatHistory.objects.filter(user_id=user_id, created_at__lt=one_hour_ago).delete()
                ChatHistory.objects.create(user_id=user_id, role='user', content=user_query)
                ChatHistory.objects.create(user_id=user_id, role='assistant', content=bot_answer)

            return JsonResponse({
                'answer': bot_answer,
                'debug_history_items': len(history)
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# -------------------------------
# BUSINESS CHAT API (SYNC FIXED)
# -------------------------------
@swagger_auto_schema(
    method='post',
    operation_description="Chat with a specific Business AI Receptionist by ID or UUID.",
    manual_parameters=[
        openapi.Parameter('business_id', openapi.IN_PATH, description="ID or UUID of the business", type=openapi.TYPE_STRING),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['message'],
        properties={
            'message': openapi.Schema(type=openapi.TYPE_STRING),
            'chat_history': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
        }
    ),
    responses={200: openapi.Response(description="AI Answer")},
    tags=['Business Chat']
)
@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def chat_api(request, business_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_query = data.get('message', '')

            if not user_query:
                return JsonResponse({'error': 'No message provided'}, status=400)

            # ✅ NEW: Use client-provided history for 100% ID-less reliability
            history = data.get('chat_history', [])
            
            # 🔥 Diagnostic LOG
            print(f"DEBUG: CHAT API | History Items Received: {len(history)}")

            # ✅ RUN AI RAG (Using the history provided by the browser)
            bot_answer = async_to_sync(aget_rag_answer_with_agent)(
                business_id,
                user_query,
                chat_history=history
            )

            # ✅ Cleanup: Delete records older than 1 hour for this user/business
            from django.utils import timezone
            from datetime import timedelta
            one_hour_ago = timezone.now() - timedelta(hours=1)

            # OPTIONAL: Save to DB for internal analytics (but AI doesn't NEED it anymore)
            user_id = data.get('user_id') or request.session.session_key
            with transaction.atomic():
                if user_id:
                    ChatHistory.objects.filter(user_id=user_id, created_at__lt=one_hour_ago).delete()
                ChatHistory.objects.create(
                    user_id=user_id, 
                    business_id=business_id, 
                    role='user', 
                    content=user_query
                )
                ChatHistory.objects.create(
                    user_id=user_id, 
                    business_id=business_id, 
                    role='assistant', 
                    content=bot_answer
                )

            return JsonResponse({
                'answer': bot_answer,
                'products': [],
                'debug_history_items': len(history)
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@swagger_auto_schema(
    method='get',
    operation_description="Page - Check Booking Status & Reviews.",
    manual_parameters=[
        openapi.Parameter('email', openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Customer Email"),
        openapi.Parameter('phone', openapi.IN_QUERY, type=openapi.TYPE_STRING, description="Customer Phone"),
    ],
    tags=['Pages']
)
@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def booking_status_view(request):
    """Page for users to check their booking status and pay."""
    from .models import Appointment
    bookings = []
    email = ""
    phone = ""
    
    if request.method == 'POST':
        email = request.data.get('email', '').strip()
        phone = request.data.get('phone', '').strip()
        if email or phone:
            query = Q()
            if email:
                query |= Q(customer_email__iexact=email)
            if phone:
                query |= Q(customer_phone=phone)
            bookings = Appointment.objects.filter(query).order_by('-start_time')

    if request.accepted_renderer.format == 'html' or 'text/html' in request.META.get('HTTP_ACCEPT', ''):
        return render(request, 'business/booking_status.html', {
            'bookings': bookings,
            'email': email,
            'phone': phone
        })
    
    return JsonResponse({
        'bookings': [
            {
                'service': b.service_name,
                'time': b.start_time.isoformat(),
                'status': b.status,
                'payment_status': b.payment_status
            } for b in bookings
        ]
    })