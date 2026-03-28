import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_reservation.settings')
django.setup()

from business.rag import build_pipeline_and_get_db
from business.models import BusinessEmbedding

print("------ RUNNING EMBEDDING PIPELINE ------")
db = build_pipeline_and_get_db()

print("\n------ CHECKING DJANGO DATABASE ------")
total_embeddings = BusinessEmbedding.objects.count()
print(f"Total rows currently in the BusinessEmbedding table: {total_embeddings}")

if total_embeddings > 0:
    first_embedding = BusinessEmbedding.objects.first()
    print(f"\nExample Record: Business -> {first_embedding.business.name}")
    # Now chunks are in a list
    chunks = first_embedding.embeddings_data
    print(f"Total chunks stored in this record: {len(chunks)}")
    
    if chunks:
        first_chunk = chunks[0]
        print(f"First Chunk Text: {first_chunk.get('text')[:100]}...")
        vector = first_chunk.get('vector')
        print(f"Vector stored? {'Yes' if vector else 'No'}, Length: {len(vector)}")
    print("--------------------------------------\n")
else:
    print("\nWarning: No embeddings found in the database. Something went wrong or no businesses exist!\n")
