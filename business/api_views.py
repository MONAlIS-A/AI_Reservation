from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Business, BusinessEmbedding, Appointment
from .serializers import BusinessSerializer, BusinessEmbeddingSerializer, AppointmentSerializer
from .rag import build_pipeline_and_get_db, aget_rag_answer_with_agent, aget_global_rag_answer
from asgiref.sync import async_to_sync
import json

class BusinessViewSet(viewsets.ModelViewSet):
    queryset = Business.objects.all()
    serializer_class = BusinessSerializer

class BusinessEmbeddingViewSet(viewsets.ModelViewSet):
    queryset = BusinessEmbedding.objects.all()
    serializer_class = BusinessEmbeddingSerializer

class AppointmentViewSet(viewsets.ModelViewSet):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer

class GlobalChatAPIView(APIView):
    """
    DRF version of the Global Multi-Business search.
    """
    authentication_classes = [] # Disable auth to avoid Session/ORM sync error in async context
    permission_classes = []

    def get(self, request):
        try:
            user_query = "Hello! Please list all available businesses with a short description of their services, and then ask me how you can help me today."
            bot_answer = async_to_sync(aget_global_rag_answer)(user_query)
            return Response({'answer': bot_answer})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        user_query = request.data.get('message', '').strip()
        if not user_query:
            user_query = "Hello! Please list all available businesses with a short description of their services, and then ask me how you can help me today."
        
        try:
            bot_answer = async_to_sync(aget_global_rag_answer)(user_query)
            return Response({'answer': bot_answer})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChatAPIView(APIView):
    """
    DRF version of the Business-specific chatbot.
    """
    authentication_classes = [] # Disable auth to avoid Session/ORM sync error in async context
    permission_classes = []

    def post(self, request, business_id):
        user_query = request.data.get('message', '')
        if not user_query:
            return Response({'error': 'No message provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            bot_answer = async_to_sync(aget_rag_answer_with_agent)(business_id, user_query)
            return Response({'answer': bot_answer, 'products': []})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CreateBusinessAPIView(APIView):
    """
    DRF version of create_business.
    """
    def post(self, request):
        serializer = BusinessSerializer(data=request.data)
        if serializer.is_valid():
            business_instance = serializer.save()
            try:
                build_pipeline_and_get_db(business_id=business_instance.id)
            except Exception as e:
                return Response({'error': f"Business created but embedding failed: {str(e)}", 'data': serializer.data}, status=status.HTTP_201_CREATED)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class BusinessDetailByNameAPIView(APIView):
    """
    DRF endpoint to get business details by name (used for chatbot/receptionist pages).
    """
    def get(self, request, business_name):
        business = get_object_or_404(Business, name__iexact=business_name)
        serializer = BusinessSerializer(business)
        return Response(serializer.data)
