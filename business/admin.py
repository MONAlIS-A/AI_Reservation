from django.contrib import admin
from .models import Business, BusinessEmbedding, Appointment, BusinessService

@admin.register(BusinessService)
class BusinessServiceAdmin(admin.ModelAdmin):
    # Displaying all 21 fields in the list view
    list_display = (
        'id', 'name', 'business', 'price', 'category', 'location', 
        'duration_minutes', 'service_type', 'currency', 'max_capacity', 
        'image_url', 'is_popular', 'biz_service_name', 'biz_phone', 
        'biz_email', 'biz_address', 'biz_city', 'biz_state', 
        'biz_country', 'biz_zip_code', 'biz_logo_url'
    )
    list_filter = ('business', 'category', 'service_type', 'is_popular')
    search_fields = ('name', 'description', 'biz_phone', 'biz_email', 'biz_city')
    
    fieldsets = (
        ('Service Information', {
            'fields': ('business', 'name', 'description', 'price', 'category', 'location', 'duration_minutes', 'service_type', 'currency', 'max_capacity', 'image_url', 'is_popular')
        }),
        ('Business Metadata (From Sync)', {
            'fields': ('biz_service_name', 'biz_phone', 'biz_email', 'biz_address', 'biz_city', 'biz_state', 'biz_country', 'biz_zip_code', 'biz_logo_url')
        }),
        ('AI Data', {
            'fields': ('embedding',),
            'classes': ('collapse',),
        }),
    )

    def has_embedding(self, obj):
        return obj.embedding is not None
    has_embedding.boolean = True
    has_embedding.short_description = 'Embedded?'

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'website_url')
    search_fields = ('name', 'website_url')

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
