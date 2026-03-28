from django.db import models

class Business(models.Model):
    name = models.CharField(max_length=255, verbose_name="Business Name", help_text="e.g. Acme Corporation")
    website_url = models.URLField(max_length=200, verbose_name="Website URL", help_text="https://www.yourbusiness.com")
    description = models.TextField(verbose_name="Description", help_text="Describe your primary business focus...")

    def __str__(self):
        return self.name

class BusinessEmbedding(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='vector_data')
    # Store a list of objects: [{"text": "chunk1", "vector": [...]}, {"text": "chunk2", "vector": [...]}]
    embeddings_data = models.JSONField(verbose_name="All Embeddings Data", default=list)

    def __str__(self):
        return f"Consolidated Embeddings for: {self.business.name}"
