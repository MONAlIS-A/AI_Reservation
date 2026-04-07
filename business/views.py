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

from django.db.models import Q

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

            # Backup Log (Stateless AI doesn't strictly need this, but good for logs)
            user_id = data.get('user_id') or request.session.session_key
            with transaction.atomic():
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

            # OPTIONAL: Save to DB for internal analytics (but AI doesn't NEED it anymore)
            user_id = data.get('user_id') or request.session.session_key
            with transaction.atomic():
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