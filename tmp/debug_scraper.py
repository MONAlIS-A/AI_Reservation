import requests
import json
from bs4 import BeautifulSoup

def scrape_business_website(url, query=""):
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list) and query:
                    q_clean = query.lower().replace("?", "").replace("is ", "").replace("available", "").strip()
                    keywords = [w for w in q_clean.split() if len(w) > 2]
                    filtered = []
                    for item in data:
                        item_str = json.dumps(item).lower()
                        if any(k in item_str for k in keywords) or q_clean in item_str:
                            filtered.append(item)
                    if filtered:
                        return f"Found matching JSON items: {json.dumps(filtered[:10], indent=2)[:12000]}"
                return f"Website API Data Found: {json.dumps(data, indent=2)[:12000]}"
            except Exception as e: 
                print(f"JSON Parse Error: {e}")
                pass
            return "HTML result (skipped for now)"
    except Exception as e: return f"Error: {e}"

url = "https://kolzsticks.github.io/Free-Ecommerce-Products-Api/main/products.json"
query = "Is Eau de Parfum - Floral Scent available? Show Name, Price, Image, Link."
print(f"SCRAPER RESULT:\n{scrape_business_website(url, query)}")
