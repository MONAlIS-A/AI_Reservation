from django.contrib import admin
from .models import Business, BusinessEmbedding

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
