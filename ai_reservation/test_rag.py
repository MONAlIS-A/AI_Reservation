import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ai_reservation.settings')
django.setup()

from business.rag import build_pipeline_and_get_db

print("Starting tests...")
# 1. Pipeline Test
vector_db = build_pipeline_and_get_db()

if vector_db:
    print("\n--------------------------")
    print("SIMILARITY SEARCH TEST")
    print("--------------------------\n")
    
    # 2. Similarity Search Test
    query = "Something related to AI and technology"
    print(f"Query: '{query}'")
    
    try:
        results = vector_db.similarity_search(query, k=2)
        print(f"\nFound {len(results)} matches!")
        for i, doc in enumerate(results):
            print(f"\nMatch #{i+1} (Business: {doc.metadata.get('name')}):")
            print(f"{doc.page_content}")
            print("-" * 20)
    except Exception as e:
        print(f"Error during search: {e}")
        
    print("\nEverything is working perfectly!")
else:
    print("\nDatabase returned None. Make sure you have at least one business saved via your form with a description!")
