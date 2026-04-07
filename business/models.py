from django.db import models

class Business(models.Model):
    name = models.CharField(max_length=255, verbose_name="Business Name", help_text="e.g. Acme Corporation")
    website_url = models.URLField(max_length=200, verbose_name="Website URL", help_text="https://www.yourbusiness.com")
    description = models.TextField(verbose_name="Description", help_text="Describe your primary business focus...")
    # domain = models.CharField(max_length=100, default="Services", choices=[
    #     ('Health & Wellness', 'Health & Wellness'),
    #     ('Personal Care & Lifestyle', 'Personal Care & Lifestyle'),
    #     ('Professional Services', 'Professional Services'),
    #     ('Hospitality & Leisure', 'Hospitality & Leisure'),
    #     ('Education & Training', 'Education & Training'),
    #     ('Services & Maintenance', 'Services & Maintenance'),
    # ])

    def __str__(self):
        return self.name

class BusinessEmbedding(models.Model):
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='vector_data')
    # Store a list of objects: [{"text": "chunk1", "vector": [...]}, {"text": "chunk2", "vector": [...]}]
    embeddings_data = models.JSONField(verbose_name="All Embeddings Data", default=list)

    def __str__(self):
        return f"Consolidated Embeddings for: {self.business.name}"

class Appointment(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='appointments')
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField(blank=True, null=True)
    service_name = models.CharField(max_length=255, default="General Service")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=50, default="confirmed") # confirmed, cancelled
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking at {self.business.name} for {self.customer_name} on {self.start_time}"

class ChatHistory(models.Model):
    session_key = models.CharField(max_length=255, db_index=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, null=True, blank=True, related_name='chat_logs')
    role = models.CharField(max_length=50) # user, assistant
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        biz_name = self.business.name if self.business else "Global Chat"
        return f"{biz_name} | {self.role} | {self.created_at}"
