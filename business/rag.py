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

def scrape_business_website(url):
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'lxml') or BeautifulSoup(response.text, 'html.parser')
            for tag in ["script", "style", "nav", "footer", "header"]:
                for s in soup(tag): s.decompose()
            clean_text = '\n'.join(line.strip() for line in soup.get_text(separator='\n').splitlines() if line.strip())
            return clean_text[:8000] 
    except Exception: return ""
    return ""

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
        # Dynamic website override from tool args if provided
        exec_url = args.get("url", website_url or args.get("url"))
        if not exec_url and exec_biz_id:
            try:
                biz = await sync_to_async(Business.objects.get)(id=exec_biz_id)
                exec_url = biz.website_url
            except Exception: pass
        return scrape_business_website(exec_url) if exec_url else "No website available."
    
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
    
    return "Unknown tool."

async def aget_rag_answer_with_agent(business_id, query):
    try:
        biz = await sync_to_async(Business.objects.get)(id=business_id)
    except Exception: return "Business not found."

    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)
    
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
                "description": "Checks business website for real-time info.",
                "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
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
        }
    ]
    
    system_prompt = f"""
    You are a professional, warm, and highly empathetic AI Receptionist for '{biz.name}' ({biz.domain}). 
    Your goal is to make the user feel welcome and well-cared for. Use friendly emojis where appropriate.

    FORMATTING RULES:
    - DO NOT use asterisks (*) or double asterisks (**) for bolding or bullet points.
    - Provide information as plain text. 
    - Use numbers (1., 2.) for lists.

    DATA COLLECTION RULES FOR BOOKING:
    - You MUST explicitly and warmly ask for these 5 things:
      1. User Name
      2. User Email
      3. Service Name (e.g., 'What service would you like at {biz.name}?')
      4. Date (YYYY-MM-DD)
      5. Time (HH:MM or HH:MM AM/PM)
    
    SERVICE DETAILS & IMAGES:
    - When a user asks about services, use 'search_documentation' and 'search_website' to find DETAILS.
    - If you find images (e.g., Markdown images ![alt](url)), always show them.
    - Describe the services with passion and explain why they are great!

    BOOKING FLOW (STRICT):
    1. Once you have ALL 5 details, YOU MUST call 'check_calendar' IMMEDIATELY for that date.
    2. Analyze the calendar data. If the specific time is NOT in the booked list, YOU MUST call 'book_appointment' IMMEDIATELY.
    3. **CRITICAL**: DO NOT tell the user to "wait", "one moment", or that you will "get back to them". 
    4. YOU MUST execute the tools and provide the FINAL confirmation or rejection in the SAME response.
    
    CONFIRMATION MESSAGE FORMAT:
       "Booking Confirmed! 🎉
       - Business: {biz.name}
       - Service: [Service Name]
       - Name: [User Name]
       - Email: [User Email]
       - Date & Time: [Date] at [Time]
       We are so excited to see you there! See you soon!"
    
    If the slot is busy, explain why kindly and suggest the next available slot immediately.
    
    GENERAL RULES:
    - Use 'search_documentation' for business info.
    - Use 'search_website' if docs don't have the answer.
    - If checking status, ask for Email and Service Name, then use 'check_booking_status'.

    Current Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query)
    ]
    
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

async def aget_global_rag_answer(query):
    """
    Agent that works across ALL businesses.
    """
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)
    
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
        }
    ]
    
    system_prompt = f"""
    You are 'Multi-Business AI Discovery'. You are warm, empathetic, and professional. 😊
    
    FORMATTING RULES:
    - DO NOT use asterisks (*) or double asterisks (**) for bolding or bullet points in business or product descriptions.
    - Provide information as plain text. 
    - Use numbers (1., 2.) for lists.
    
    GREETING & DISCOVERY:
    - Welcome the user warmly and introduce yourself briefly as the AI Discovery Assistant.
    - When the user greets you or asks for a list, you MUST provide a full list of ALL available businesses and their descriptions.
    - ALWAYS use the tool 'search_across_businesses' with 'query=list all' to get this data.
    - For each business, carefully read the retrieved database context and provide a brief, engaging summary of what it offers based ONLY on its description.
    
    TASK 1: Global Information Retrieval (STRICT REQUIRED STEP)
    - Whenever the user asks ANY question about finding a service, business, product, or booking (e.g., "I want a haircut", "food", "doctors"), you MUST IMMEDIATELY execute the tool 'search_across_businesses' with their specific query.
    - NEVER say "I don't know" or "I cannot see the database" without calling the tool first.
    - Carefully read the retrieved context from the tool. Summarize the matching business NAMES and their offerings based ONLY on the retrieved details.
    - Ask the user to choose ONE of the summarized businesses to proceed.
    - If no relevant business is found in the tool's response, politely inform them.
    
    TASK 2: Business Choice & AI Receptionist Handoff
    - If the user explicitly wants to take a service, schedule an appointment, or talk directly to a specific business:
    - Immediately provide the DIRECT CLICKABLE LINK to that business's dedicated AI Receptionist.
    - FORMAT: [Click here to chat with {{Business Name}} AI Receptionist](/receptionist/{{Slug}}/)
    - Example: "Great choice! 😊 You can now chat directly with the Rooftop receptionist here to finalize your booking: [Click here to chat with Rooftop AI Receptionist](/receptionist/rooftop/)"
    - Do not perform the booking yourself. The dedicated AI Receptionist handles bookings and detailed conversations.
    
    Current Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query)
    ]
    
    chat_with_tools = llm.bind_tools(tools)
    
    for _ in range(5):
        try:
            response = await chat_with_tools.ainvoke(messages)
            messages.append(response)
            if not response.tool_calls:
                break
            for tool_call in response.tool_calls:
                # Use None for defaults as the tools should now specify IDs in args
                res = await run_tool(tool_call["name"], tool_call["args"], None, None)
                messages.append(ToolMessage(tool_call_id=tool_call["id"], content=str(res)))
        except Exception as e:
            return f"Error: {str(e)}"

    return messages[-1].content

def get_rag_answer_with_agent(business_id, query):
    import asyncio
    return asyncio.run(aget_rag_answer_with_agent(business_id, query))
