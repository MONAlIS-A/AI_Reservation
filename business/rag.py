from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from asgiref.sync import sync_to_async
from bs4 import BeautifulSoup
import requests
import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()

from .models import Business
from .calendar_service import get_slots, book_appointment, check_booking_status

# --- RAG Utils ---
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

def load_business_documents(business_id=None):
    if business_id:
        businesses = Business.objects.filter(id=business_id)
    else:
        businesses = Business.objects.all()
    docs = []
    for biz in businesses:
        if biz.description:
            text = f"Business Name: {biz.name}\nDescription: {biz.description}\nDomain: {biz.domain}"
            docs.append(Document(page_content=text, metadata={"business_id": biz.id, "business_name": biz.name}))
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
    
    # Simple logic: If it's a multi-business chunking, we don't save a single OneToOne
    if len(set([c.metadata.get("business_id") for c in chunks])) == 1:
        biz_id = chunks[0].metadata.get("business_id")
        if biz_id:
            BusinessEmbedding.objects.update_or_create(business_id=biz_id, defaults={'embeddings_data': all_embeddings_list})
    
    return FAISS.from_documents(chunks, embeddings)

def build_pipeline_and_get_db(business_id=None):
    docs = load_business_documents(business_id)
    if not docs: return None
    chunks = split_documents(docs)
    return generate_vector_db(chunks)

def scrape_business_website(url, query=""):
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            # Try JSON first
            try:
                data = response.json()
                if isinstance(data, list) and query:
                    import re
                    q_clean = re.sub(r'[^\w\s]', '', query.lower())
                    stop_words = {'is', 'are', 'available', 'available', 'show', 'name', 'price', 'image', 'link', 'details', 'for', 'the', 'and'}
                    keywords = [w for w in q_clean.split() if len(w) > 2 and w not in stop_words]
                    scored_items = []
                    for item in data:
                        item_str = json.dumps(item).lower()
                        score = sum(1 for k in keywords if k in item_str)
                        if score > 0: scored_items.append((score, item))
                    if scored_items:
                        scored_items.sort(key=lambda x: x[0], reverse=True)
                        return json.dumps([x[1] for x in scored_items[:2]], indent=2)
                return json.dumps(data, indent=2)[:15000]
            except Exception:
                pass
            
            # Case HTML
            soup = BeautifulSoup(response.text, 'lxml') or BeautifulSoup(response.text, 'html.parser')
            for tag in ["script", "style"]:
                for s in soup(tag): s.decompose()
            elements = []
            for img in soup.find_all('img', src=True):
                alt = img.get('alt', 'Product Image')
                src = img['src']
                if not src.startswith('http'): src = f"{url.rstrip('/')}/{src.lstrip('/')}"
                elements.append(f"Image: ![ {alt} ]({src})")
            for a in soup.find_all('a', href=True):
                title = a.get_text().strip() or "View Link"
                href = a['href']
                if not href.startswith('http'): href = f"{url.rstrip('/')}/{href.lstrip('/')}"
                elements.append(f"Link: [ {title} ]({href})")
            clean_text = soup.get_text(separator=' ')
            full_context = f"Website Text Content: {clean_text[:4000]}\n\nFound Media/Links:\n" + "\n".join(elements[:30])
            return full_context[:8000] 
    except Exception: return "Error scraping the target URL."
    return "No content retrieved."

# --- Manual Tool Runner ---
async def run_tool(name, args, business_id=None, website_url=None):
    # Dynamic business_id override from tool args if provided
    exec_biz_id = args.get("business_id", business_id)
    
    if name == "search_documentation":
        try:
            vector_db = await sync_to_async(build_pipeline_and_get_db)(business_id=exec_biz_id)
            if vector_db:
                sim_docs = vector_db.similarity_search(args.get("query", ""), k=3)
                return "\n".join([d.page_content for d in sim_docs])
        except Exception as e: return f"Error: {str(e)}"
        return "No docs found."
    
    elif name == "search_website":
        # Dynamic website and query override
        exec_url = args.get("url", website_url)
        search_query = args.get("query", "")
        if not exec_url and exec_biz_id:
            try:
                biz = await sync_to_async(Business.objects.get)(id=exec_biz_id)
                exec_url = biz.website_url
            except Exception: pass
        if not exec_url: return "No website available to search."
        
        content = scrape_business_website(exec_url, query=search_query)
        return content
    
    elif name == "check_calendar":
        res = await sync_to_async(get_slots)(exec_biz_id, args.get('date'))
        return json.dumps(res)
    
    elif name == "book_appointment":
        res = await sync_to_async(book_appointment)(
            exec_biz_id, 
            args.get('customer_name'), 
            args.get('customer_email'),
            args.get('service_name'),
            args.get('start_time')
        )
        return json.dumps(res)

    elif name == "search_across_businesses":
        try:
            # Query all businesses' docs
            if args.get("query", "").lower() in ["list all", "hello", "hi", "all businesses"]:
                businesses = await sync_to_async(lambda: list(Business.objects.all()))()
                results = []
                for biz in businesses:
                    results.append(f"Business ID: {biz.id} | Name: {biz.name} | Slug: {biz.name} | Domain: {biz.domain} | Desc: {str(biz.description)[:100]}...")
                return "\n".join(results)
            
            vector_db = await sync_to_async(build_pipeline_and_get_db)(business_id=None)
            if vector_db:
                sim_docs = vector_db.similarity_search(args.get("query", ""), k=5)
                results = []
                for d in sim_docs:
                    biz_id = d.metadata.get('business_id')
                    biz_name = d.metadata.get('business_name')
                    biz = await sync_to_async(Business.objects.get)(id=biz_id)
                    results.append(f"Business: {biz_name} (Slug: {biz.name})\nDetails Section: {d.page_content}")
                return "\n---\n".join(results)
        except Exception as e: return f"Error: {str(e)}"
        return "No businesses found matching this query."

    elif name == "check_booking_status":
        res = await sync_to_async(check_booking_status)(
            args.get('email'),
            args.get('service_name')
        )
        return json.dumps(res)
    
    elif name == "web_search":
        try:
            from langchain_community.tools import DuckDuckGoSearchRun
            search = DuckDuckGoSearchRun()
            return search.run(args.get("query", ""))
        except Exception as e:
            return f"Web search error: {str(e)}"
    
    return "Unknown tool."

async def aget_rag_answer_with_agent(business_id, query, chat_history=None):
    try:
        biz = await sync_to_async(Business.objects.get)(id=business_id)
    except Exception: return "Business not found."

    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.5)
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_documentation",
                "description": "Checks internal docs for the current business.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_website",
                "description": "Search the business website for specific real-time info like products, prices, and links.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "url": {"type": "string"},
                        "query": {"type": "string"}
                    }, 
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_calendar",
                "description": "Check booked slots for a specific date (YYYY-MM-DD).",
                "parameters": {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "book_appointment",
                "description": "Permanently save a booking to the database once a slot is confirmed to be available.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "customer_name": {"type": "string"},
                        "customer_email": {"type": "string"},
                        "service_name": {"type": "string"},
                        "start_time": {"type": "string", "description": "ISO format (e.g. 2024-12-01T10:00:00)"}
                    },
                    "required": ["customer_name", "customer_email", "service_name", "start_time"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_booking_status",
                "description": "Find existing booking by email and service name.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "email": {"type": "string"},
                        "service_name": {"type": "string"}
                    },
                    "required": ["email", "service_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Searches the internet for product prices, images, and links if not found locally.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
            }
        }
    ]
    
    system_prompt = f"""
    INTENT & QUERY ANALYSIS:
    - Step 1: Detect User Intent. 
    - **Intent A (Inquiry)**: If user asks about availability or prices (e.g. "Is X available?").
      - YOU MUST: Search docs/website. 
      - YOU MUST: Clearly display: **Product Name**, **Price** (if cent, convert to $), **Markdown Image**, and **Clickable Link**.
      - **CRITICAL**: Do NOT mention booking or data collection yet.
    - **Intent B (Booking)**: ONLY if user explicitly says they want to book or reserve, transition to DATA COLLECTION. 
    
    OPERATIONAL GUIDELINES:
    - For inquiries: Show the product information cards/text clearly. STOP there.
    - If a user says "X is available", accept it and move to Intent B.
    - Price Conversion: `priceCents` 3500 becomes `$35.00`.
    - No emotional fillers. Strictly professional.
    
    SHORT MEMORY & CONTEXT:
    - Identify details. Convert 'tomorrow' to `YYYY-MM-DD`.
    
    FORMATTING: No asterisks. No emojis. Numbers for lists.

    SHORT MEMORY & CONTEXT:
    - Automatically identify or calculate details (Name, Email, Service, Date, Time).
    - Convert relative dates like 'tomorrow' into `YYYY-MM-DD` using current time.

    FORMATTING RULES:
    - No asterisks. No emojis. Plain text only. Use numbers for lists.

    DATA COLLECTION & PARAMETERS (FOR BOOKING):
    1. Your full name (Map to `customer_name`)
    2. Your email address (Map to `customer_email`)
    3. The service name (Map to `service_name`)
    4. Date (YYYY-MM-DD format)
    5. Time (HH:MM format)
    
    - **CRITICAL**: Combine Date and Time into ISO string `YYYY-MM-DDTHH:MM:SS` for the 'start_time' parameter.
    
    BOOKING EXECUTION (STRICT):
    1. Check Slot: Call 'check_calendar' for the specified date once you have the 5 parameters.
    2. Confirm: If the tool result shows the slot is free, call 'book_appointment' IMMEDIATELY.
    3. Busy: If the tool result shows the slot is occupied, inform the user and suggest next slots.
    4. NO CONFIRMATION: Do not ask for user permission before executing these tools.

    CONFIRMATION FORMAT (REQUIRED):
       Booking Confirmed:
       1. Business: {biz.name}
       2. Service: [Service Name]
       3. Name: [User Name]
       4. Email: [User Email]
       5. Date & Time: [Date] at [Time]
    
    GENERAL RULES:
    - Use 'search_documentation' for technical business info.
    - Use 'search_website' for external links if needed.
    - For status checks, use 'check_booking_status' with the provided email.

    Current Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    messages = [SystemMessage(content=system_prompt)]
    
    # Add history
    if chat_history:
        for msg in chat_history:
            if msg.get('role') == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg.get('role') == 'assistant':
                messages.append(AIMessage(content=msg['content']))
                
    messages.append(HumanMessage(content=query))
    
    chat_with_tools = llm.bind_tools(tools)
    
    for _ in range(5):
        try:
            response = await chat_with_tools.ainvoke(messages)
            messages.append(response)
            if not response.tool_calls:
                break
            for tool_call in response.tool_calls:
                res = await run_tool(tool_call["name"], tool_call["args"], business_id, biz.website_url)
                messages.append(ToolMessage(tool_call_id=tool_call["id"], content=str(res)))
        except Exception as e:
            return f"I had a tiny problem: {str(e)}"

    return messages[-1].content

async def aget_global_rag_answer(query, chat_history=None):
    """
    Agent that works across ALL businesses.
    """
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.5)
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_across_businesses",
                "description": "Identifies businesses that provide a service. Use 'query=list all' to get the full directory of available businesses.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_documentation",
                "description": "Get details for a specific business by its ID.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "business_id": {"type": "integer"},
                        "query": {"type": "string"}
                    }, 
                    "required": ["business_id", "query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_website",
                "description": "Search the website of a specific business by its ID.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "business_id": {"type": "integer"},
                        "url": {"type": "string"}
                    }, 
                    "required": ["business_id", "url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_booking_status",
                "description": "Find existing booking across all businesses by email and service name.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "email": {"type": "string"},
                        "service_name": {"type": "string"}
                    },
                    "required": ["email", "service_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Searches the internet for products, prices, and links.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
            }
        }
    ]
    
    system_prompt = f"""
    You are 'Multi-Business AI Discovery'. You are professional, empathetic, and direct. 😊
    
    SHORT MEMORY & CONTEXT:
    - Use conversation history to guide the user.
    
    FORMATTING RULES:
    - No asterisks. Plain text only. Use numbers for lists.
    
    GREETING & DISCOVERY:
    - ALWAYS use 'search_across_businesses' with 'query=list all' if greeting the user.
    - If a user asks for a specific product, use 'web_search' or 'search_website' if you have the business ID.
    
    TASK 1: Global Information Retrieval
    - If user asks for any service/product info, search documentation and website first, then fallback to 'web_search'.
    - If found: You MUST show Name, Price, Image, and Link.
    
    TASK 2: Handoff
    - Provide the direct chat link: [/receptionist/{{Slug}}/]
    
    Current Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """

    messages = [SystemMessage(content=system_prompt)]
    
    if chat_history:
        for msg in chat_history:
            if msg.get('role') == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg.get('role') == 'assistant':
                messages.append(AIMessage(content=msg['content']))

    messages.append(HumanMessage(content=query))
    
    chat_with_tools = llm.bind_tools(tools)
    
    for _ in range(5):
        try:
            response = await chat_with_tools.ainvoke(messages)
            messages.append(response)
            if not response.tool_calls:
                break
            for tool_call in response.tool_calls:
                res = await run_tool(tool_call["name"], tool_call["args"], None, None)
                messages.append(ToolMessage(tool_call_id=tool_call["id"], content=str(res)))
        except Exception as e:
            return f"Error: {str(e)}"

    return messages[-1].content

def get_rag_answer_with_agent(business_id, query, chat_history=None):
    import asyncio
    return asyncio.run(aget_rag_answer_with_agent(business_id, query, chat_history))
