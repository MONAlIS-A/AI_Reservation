from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .forms import BusinessForm
from .models import Business, ChatHistory
from .rag import build_pipeline_and_get_db, aget_rag_answer_with_agent, aget_global_rag_answer
from asgiref.sync import async_to_sync
import json


# -------------------------------
# Business Creation
# -------------------------------
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
def chatbot_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    return render(request, 'business/chatbot.html', {'business': business})


def receptionist_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    return render(request, 'business/receptionist.html', {'business': business})


def ai_call_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    return render(request, 'business/ai_call.html', {'business': business})


def global_chat_page(request):
    return render(request, 'business/global_chat.html')


from django.db import transaction

def global_chat_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_query = data.get('message', '').strip() or "Hello!"
            
            # 🔥 Hardened Identity Logic
            user_id = data.get('user_id') or data.get('session_id') 
            if not user_id or user_id == "undefined":
                if not request.session.session_key:
                    request.session.save()
                user_id = request.session.session_key
            
            # Diagnostic LOG
            print(f"DEBUG: GLOBAL CHAT | UserID: {user_id}")

            # 1. SAVE USER MESSAGE FIRST (to be in context)
            with transaction.atomic():
                ChatHistory.objects.create(user_id=user_id, role='user', content=user_query)

            # 2. LOAD HISTORY FOR RAG
            db_history = ChatHistory.objects.filter(
                user_id=user_id,
                business__isnull=True
            ).order_by('created_at')
            history_count = db_history.count()
            history = [{'role': h.role, 'content': h.content} for h in db_history]

            # 3. RUN AI RAG
            bot_answer = async_to_sync(aget_global_rag_answer)(
                user_query,
                chat_history=history
            )

            # 4. SAVE ASSISTANT RESPONSE
            with transaction.atomic():
                ChatHistory.objects.create(user_id=user_id, role='assistant', content=bot_answer)

            return JsonResponse({
                'answer': bot_answer,
                'debug_user_id': user_id,
                'debug_history_items': history_count
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# -------------------------------
# BUSINESS CHAT API (SYNC FIXED)
# -------------------------------
def chat_api(request, business_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_query = data.get('message', '')

            if not user_query:
                return JsonResponse({'error': 'No message provided'}, status=400)

            # 🔥 Hardened Identity Logic
            user_id = data.get('user_id') or data.get('session_id')
            if not user_id or user_id == "undefined":
                if not request.session.session_key:
                    request.session.save()
                user_id = request.session.session_key

            # 1. SAVE USER MESSAGE FIRST
            with transaction.atomic():
                ChatHistory.objects.create(user_id=user_id, business_id=business_id, role='user', content=user_query)

            # 2. LOAD history from Database
            db_history = ChatHistory.objects.filter(
                user_id=user_id,
                business_id=business_id
            ).order_by('created_at')
            history_count = db_history.count()
            history = [{'role': h.role, 'content': h.content} for h in db_history]

            # 3. RUN AI RAG
            bot_answer = async_to_sync(aget_rag_answer_with_agent)(
                business_id,
                user_query,
                chat_history=history
            )

            # 4. SAVE ASSISTANT RESPONSE
            with transaction.atomic():
                ChatHistory.objects.create(user_id=user_id, business_id=business_id, role='assistant', content=bot_answer)

            return JsonResponse({
                'answer': bot_answer,
                'products': [],
                'debug_user_id': user_id,
                'debug_history_items': history_count
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)