from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .forms import BusinessForm
from .models import Business
from .rag import build_pipeline_and_get_db, get_rag_answer_with_agent
import json
import re

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

def chatbot_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    return render(request, 'business/chatbot.html', {'business': business})

def receptionist_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    return render(request, 'business/receptionist.html', {'business': business})

def ai_call_page(request, business_name):
    business = get_object_or_404(Business, name__iexact=business_name)
    return render(request, 'business/ai_call.html', {'business': business})

def chat_api(request, business_id):
    """
    এন্ডপয়েন্ট যা এখন LangChain Agent ব্যবহার করবে DuckDuckGo সার্চের মাধ্যমে।
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_query = data.get('message', '')
            
            if not user_query:
                return JsonResponse({'error': 'No message provided'}, status=400)
                
            # এপিআই এজেন্ট কল করা হচ্ছে (RAG + Live Search)
            bot_answer = get_rag_answer_with_agent(business_id, user_query)
            
            return JsonResponse({
                'answer': bot_answer,
                'products': [] # এজেন্টের উত্তরে লিংক/ছবি টেক্সট আকারেই থাকবে
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Invalid request method'}, status=405)