from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .models import Business, BusinessEmbedding, Appointment
from .serializers import BusinessSerializer, BusinessEmbeddingSerializer, AppointmentSerializer
from .rag import build_pipeline_and_get_db, aget_rag_answer_with_agent, aget_global_rag_answer
from asgiref.sync import async_to_sync
import json


class BusinessViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for Business entities.
    
    list: Returns all registered businesses.
    create: Register a new business.
    retrieve: Get a specific business by ID.
    update: Update a business record.
    destroy: Delete a business record.
    """
    queryset = Business.objects.all()
    serializer_class = BusinessSerializer


class BusinessEmbeddingViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for Business Embedding vectors.
    
    Manages the RAG vector embeddings stored for each business.
    """
    queryset = BusinessEmbedding.objects.all()
    serializer_class = BusinessEmbeddingSerializer


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for Appointments.
    
    list: View all appointments.
    create: Create a new appointment.
    retrieve: Get a specific appointment.
    update: Modify an appointment.
    destroy: Cancel an appointment.
    """
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer


class GlobalChatAPIView(APIView):
    """
    Global AI Discovery Assistant.
    Supports both GET (auto-greeting with business list) and POST (user message) requests.
    """
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Auto-greeting: Returns a list of all available businesses with descriptions.",
        responses={
            200: openapi.Response(
                description="AI-generated greeting with business list",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'answer': openapi.Schema(type=openapi.TYPE_STRING, description='AI response with business listings'),
                    }
                )
            ),
            500: openapi.Response(description="Internal server error"),
        },
        tags=['Global Chat']
    )
    def get(self, request):
        try:
            user_query = "Hello! Please list all available businesses with a short description of their services, and then ask me how you can help me today."
            bot_answer = async_to_sync(aget_global_rag_answer)(user_query)
            return Response({'answer': bot_answer})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_description="Send a message to the Global AI Discovery Agent. "
                              "The agent searches across all businesses and helps users find services.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['message'],
            properties={
                'message': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='User message to the AI discovery agent',
                    default='Hello, what businesses are available?'
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="AI-generated response",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'answer': openapi.Schema(type=openapi.TYPE_STRING, description='AI response'),
                    }
                )
            ),
            500: openapi.Response(description="Internal server error"),
        },
        tags=['Global Chat']
    )
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
    Business-specific AI Receptionist Chatbot.
    """
    authentication_classes = []
    permission_classes = []

    @swagger_auto_schema(
        operation_description="Send a message to a specific business's AI Receptionist. "
                              "The agent can answer questions, check calendar availability, and book appointments.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['message'],
            properties={
                'message': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description='User message to the AI receptionist',
                    default='What services do you offer?'
                ),
            },
        ),
        responses={
            200: openapi.Response(
                description="AI receptionist response",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'answer': openapi.Schema(type=openapi.TYPE_STRING, description='AI response'),
                        'products': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT), description='Related products (if any)'),
                    }
                )
            ),
            400: openapi.Response(description="No message provided"),
            500: openapi.Response(description="Internal server error"),
        },
        manual_parameters=[
            openapi.Parameter('business_id', openapi.IN_PATH, description="ID of the business", type=openapi.TYPE_INTEGER),
        ],
        tags=['Business Chat']
    )
    def post(self, request, business_id):
        user_query = request.data.get('message', '')
        if not user_query:
            return Response({'error': 'No message provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            history = request.data.get('history', [])
            bot_answer = async_to_sync(aget_rag_answer_with_agent)(business_id, user_query, chat_history=history)
            return Response({'answer': bot_answer, 'products': []})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateBusinessAPIView(APIView):
    """
    Register a new business and auto-generate RAG embeddings.
    """
    @swagger_auto_schema(
        operation_description="Create a new business entity. Automatically generates vector embeddings from the business description for RAG retrieval.",
        request_body=BusinessSerializer,
        responses={
            201: openapi.Response(description="Business created successfully", schema=BusinessSerializer),
            400: openapi.Response(description="Validation error"),
        },
        tags=['Business Management']
    )
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
    Get business details by name (used for chatbot/receptionist pages).
    """
    @swagger_auto_schema(
        operation_description="Retrieve business details by its name. Used to load data for chatbot, receptionist, and call interfaces.",
        responses={
            200: openapi.Response(description="Business details", schema=BusinessSerializer),
            404: openapi.Response(description="Business not found"),
        },
        manual_parameters=[
            openapi.Parameter('business_name', openapi.IN_PATH, description="Name of the business (case-insensitive)", type=openapi.TYPE_STRING),
        ],
        tags=['Business Management']
    )
    def get(self, request, business_name):
        business = get_object_or_404(Business, name__iexact=business_name)
        serializer = BusinessSerializer(business)
        return Response(serializer.data)
