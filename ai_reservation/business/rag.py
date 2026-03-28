import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv, find_dotenv

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_community.tools import DuckDuckGoSearchRun

from .models import Business

# Load environment variables
load_dotenv(find_dotenv(), override=True)


def load_business_documents(business_id=None):
    if business_id:
        businesses = Business.objects.filter(id=business_id)
    else:
        businesses = Business.objects.all()

    docs = []
    for biz in businesses:
        if biz.description:
            text = f"Business Name: {biz.name}\nDescription: {biz.description}\nWebsite: {biz.website_url}"
            docs.append(Document(
                page_content=text, 
                metadata={"business_id": biz.id}
            ))
    return docs


def split_documents(docs):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    return text_splitter.split_documents(docs)


def generate_vector_db(chunks):
    from .models import BusinessEmbedding
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    texts = [chunk.page_content for chunk in chunks]
    if not texts: return None
        
    vectors = embeddings.embed_documents(texts)
    all_embeddings_list = [{"text": t, "vector": v} for t, v in zip(texts, vectors)]

    biz_id = chunks[0].metadata.get("business_id")
    if biz_id:
        BusinessEmbedding.objects.update_or_create(
            business_id=biz_id,
            defaults={'embeddings_data': all_embeddings_list}
        )
    
    vectorstore = FAISS.from_documents(chunks, embeddings)
    return vectorstore


def build_pipeline_and_get_db(business_id=None):
    docs = load_business_documents(business_id)
    if not docs: return None
    chunks = split_documents(docs)
    return generate_vector_db(chunks)


# --- DIRECT WEBSITE SCRAPER ---
def scrape_business_website(url):
    """
    ভয়েস বা চ্যাট এজেন্ট যখন প্রোডাক্ট খুঁজবে, তখন এটি ডাইরেক্ট ওয়েবসাইট ভিজিট করবে।
    """
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'lxml') or BeautifulSoup(response.text, 'html.parser')
            # অপ্রয়োজনীয় ট্যাগগুলো বাদ দিচ্ছি
            for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
                script_or_style.decompose()

            # শুধু টেক্সট নিয়ে নিচ্ছি (যাতে প্রোডাক্ট ডাটা থাকে)
            text = soup.get_text(separator='\n')
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)
            return clean_text[:8000] # লিমিটেড টেক্সট নিচ্ছি প্রম্পটের জন্য
    except Exception as e:
        print(f"Scraping error: {e}")
    return ""


def get_rag_answer_with_agent(business_id, query):
    """
    এআই এজেন্ট যা ডাটাবেস লিংক থেকে সরাসরি ওয়েবসাইট স্ক্র্যাপ করে এবং চ্যাট এনালাইসিস করে।
    """
    try:
        biz = Business.objects.get(id=business_id)
    except:
        return "I'm sorry, I couldn't find any information about this business."

    # ১. আরএজি থেকে ইন্টারনাল ডাটা নেওয়া
    context = ""
    try:
        vector_db = build_pipeline_and_get_db(business_id=business_id)
        if vector_db:
            sim_docs = vector_db.similarity_search(query, k=3)
            context = "\n".join([d.page_content for d in sim_docs])
    except:
        context = "No internal context found."

    # ২. ডাইরেক্ট ওয়েবসাইট স্ক্র্যাপিং (সবচেয়ে রিয়েল-টাইম প্রোডাক্ট ডাটার জন্য)
    website_scraped_data = scrape_business_website(biz.website_url)

    # ৩. ব্যাকআপ হিসেবে ডাকডাকগো সার্চ
    internet_results = ""
    try:
        search_tool = DuckDuckGoSearchRun()
        search_query = f"{biz.name} {query} products info"
        internet_results = search_tool.run(search_query)
    except:
        internet_results = "Live search results unavailable."

    # ৪. এলএলএম এর জন্য সুশৃঙ্খল প্রম্পট
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.5)
    
    final_prompt = f"""
    You are the Senior AI Sales Representative for "{biz.name}". 
    The business website URL: {biz.website_url}.
    
    TASKS:
    1. ANALYZE the conversation. If the user asks for product details, PRICE, or AVAILABILITY, find them from the provided data.
    2. Use the SCRAPED WEBSITE CONTENT as your primary source for products.
    3. Supplement with INTERNET SEARCH results if needed.
    4. Provide direct links from the website for specific products.
    
    SCRAPED WEBSITE CONTENT:
    ---
    {website_scraped_data}
    ---
    
    INTERNET SEARCH RESULTS:
    {internet_results}
    
    INTERNAL DATABASE INFO:
    {context}
    
    USER QUESTION:
    {query}
    
    ANSWER:
    """

    try:
        res = llm.invoke(final_prompt)
        return res.content
    except Exception as e:
        return f"Technical error: {str(e)}"
