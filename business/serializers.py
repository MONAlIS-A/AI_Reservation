from rest_framework import serializers
from .models import Business, BusinessEmbedding, Appointment

class BusinessEmbeddingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessEmbedding
        fields = ['id', 'embeddings_data']

class BusinessSerializer(serializers.ModelSerializer):
    vector_data = BusinessEmbeddingSerializer(read_only=True)
    
    class Meta:
        model = Business
        fields = ['id', 'name', 'website_url', 'description', 'vector_data']

class AppointmentSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business.name', read_only=True)
    
    class Meta:
        model = Appointment
        fields = ['id', 'business', 'business_name', 'customer_name', 'customer_email', 'service_name', 'start_time', 'end_time', 'status', 'created_at']
