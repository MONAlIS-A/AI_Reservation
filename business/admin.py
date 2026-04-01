from django.contrib import admin
from .models import Business, BusinessEmbedding, Appointment

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'domain', 'website_url')
    search_fields = ('name', 'website_url', 'domain')

@admin.register(BusinessEmbedding)
class BusinessEmbeddingAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'chunk_count')
    def chunk_count(self, obj):
        return f"{len(obj.embeddings_data)} chunks"
    chunk_count.short_description = 'Total Chunks'

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'business', 'customer_name', 'start_time', 'end_time', 'status')
    list_filter = ('business', 'status', 'start_time')
    search_fields = ('customer_name', 'customer_email')
