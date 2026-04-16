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

from .models import Business, ChatHistory
from .calendar_service import get_slots, book_appointment, check_booking_status

# --- RAG Utils ---
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

def load_business_documents(business_id=None):
    if business_id:
        if str(business_id).isdigit():
            businesses = Business.objects.filter(id=int(business_id))
        else:
            businesses = Business.objects.filter(external_uuid=business_id)
    else:
        businesses = Business.objects.all()
    docs = []
    for biz in businesses:
        if biz.description:
            text = f"Business Name: {biz.name}\nDescription: {biz.description}"
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
            # Try JSON first (API URL logic)
            try:
                data = response.json()
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    # Look for likely list keys
                    for key in ['products', 'items', 'data', 'results', 'objects']:
                        if isinstance(data.get(key), list):
                            items = data[key]
                            break
                    if not items: # Case it's just a single object
                        items = [data]
                
                if items:
                    # Smart Filtering: If query is provided, filter the JSON items first
                    if query and len(items) > 1:
                        query_lower = query.lower()
                        items = [
                            it for it in items 
                            if query_lower in str(it.get('name', '')).lower() or 
                               query_lower in str(it.get('description', '')).lower() or
                               any(query_lower in str(kw).lower() for kw in it.get('keywords', []))
                        ]

                    products = []
                    for item in items[:15]: # Limit to 15
                        if not isinstance(item, dict): continue
                        name = item.get('name') or item.get('title') or "Unknown Product"
                        
                        # Handle varied price keys
                        price = item.get('price') or item.get('amount') or item.get('sale_price') or item.get('priceCents')
                        if item.get('priceCents'):
                            price = f"${item.get('priceCents')/100:.2f}"
                        if not price: price = "N/A"

                        image = item.get('image') or item.get('thumbnail') or item.get('img_url') or item.get('picture') or ""
                        link = item.get('link') or item.get('url') or item.get('product_url') or url
                        
                        prod_str = f"Product: {name}\nPrice: {price}\n"
                        if image: prod_str += f"Image: ![ {name} ]({image})\n"
                        prod_str += f"Link: [ View Product ]({link})\n"
                        products.append(prod_str)
                    
                    if products:
                        return "Found products from API:\n\n" + "\n---\n".join(products)
                return json.dumps(data, indent=2)[:15000]
            except Exception:
                pass
            
            # Case HTML (Website Link logic - though prompt will usually bypass this)
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
            full_context = f"Website Content: {clean_text[:4000]}\n\nMedia/Links:\n" + "\n".join(elements[:20])
            return full_context[:8000] 
    except Exception as e: return f"Error accessing URL: {str(e)}. Please visit the website directly for info."
    return f"No content retrieved. You can visit the link here: {url}"

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
        if (not exec_url or exec_url == "null") and exec_biz_id:
            try:
                if str(exec_biz_id).isdigit():
                    biz = await sync_to_async(Business.objects.filter(id=int(exec_biz_id)).first)()
                else:
                    biz = await sync_to_async(Business.objects.filter(external_uuid=exec_biz_id).first)()
                if biz: exec_url = biz.website_url
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
            # Enhanced multi-business directory
            if args.get("query", "").lower() in ["list all", "hello", "hi", "all businesses", "identify yourself"]:
                businesses = await sync_to_async(lambda: list(Business.objects.all()))()
                from urllib.parse import quote
                results = []
                for biz in businesses:
                    encoded_name = quote(biz.name)
                    # Create a clean: **Service** — [Business Name](Link) format
                    # Using description as service for now
                    service_summary = str(biz.description).split('.')[0][:50]
                    results.append(f"- **{service_summary}** — [{biz.name}](https://ai-reservation.onrender.com/receptionist/{encoded_name}/)")
                
                header = "## 🌐 Partner Network Directory\nHere are the available services across our partner network:\n\n"
                footer = "\n\nPlease let me know which service or business you are interested in!"
                return header + "\n".join(results) + footer
            
            vector_db = await sync_to_async(build_pipeline_and_get_db)(business_id=None)
            if vector_db:
                sim_docs = vector_db.similarity_search(args.get("query", ""), k=6)
                results = []
                from urllib.parse import quote
                for d in sim_docs:
                    biz_id = d.metadata.get('business_id')
                    biz_name = d.metadata.get('business_name')
                    biz_url = "Unknown"
                    try:
                        if str(biz_id).isdigit():
                            biz_obj = await sync_to_async(Business.objects.filter(id=int(biz_id)).first)()
                        else:
                            biz_obj = await sync_to_async(Business.objects.filter(external_uuid=biz_id).first)()
                        if biz_obj: biz_url = biz_obj.website_url
                    except: pass
                    encoded_name = quote(biz_name)
                    results.append(f"Business: {biz_name} (ID: {biz_id}, URL: {biz_url}, EncodedName: {encoded_name})\nSummary: {d.page_content}")
                return "Relevant matches found across the partner network:\n\n" + "\n---\n".join(results)
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

async def asummarize_chat_history(chat_history):
    """
    Summarizes long chat history into a few critical sentences to save tokens and maintain context.
    """
    if not chat_history or len(chat_history) < 6:
        return ""
    
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history])
    
    summary_prompt = f"""
    The following is a chat history. Summarize the core facts about the user (NAME, EMAIL, INTERESTS, PREVIOUS TOPICS) 
    in 3-4 professional sentences. This will be used as long-term memory.
    
    Chat: 
    {history_text}
    
    Summary: 
    """
    try:
        res = await llm.ainvoke([SystemMessage(content=summary_prompt)])
        return res.content
    except Exception:
        return ""

async def agenerate_suggestions(answer):
    """
    Generates 3 smart, analytical follow-up suggestions based on the AI's response.
    It predicts the user's next logical step (e.g., pricing for products, booking for services).
    """
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)
        prompt = f"""
        You are a Strategic Question Generator. Analyze the AI Response below and provided context to generate EXACTLY 3 full-sentence follow-up questions.
        
        CRITICAL RULES:
        1. FORM: Each suggestion must be a clear, professional QUESTION (e.g., "What are the specific pricing plans for...?")
        2. CONTEXT: Only ask questions that the AI can answer based on the businesses or services mentioned in the response.
        3. VALUE: The questions should help the user get the most important information (Pricing, Booking, Services) from the documentation.
        4. RELIABILITY: Ensure the user's next click leads to a useful, accurate answer from the system.

        AI Response: 
        {answer}

        Suggestions (3 '|' separated full questions):
        """
        res = await llm.ainvoke([SystemMessage(content=prompt)])
        text = res.content.replace('"', '').replace("'", "")
        # Use pipe separator instead of comma to handle questions with commas
        suggestions = [s.strip() for s in text.split("|") if s.strip()]
        
        # Ensure exactly 3 items
        if len(suggestions) < 3:
            suggestions.extend(["Tell me more", "Pricing details", "How to book"][:3-len(suggestions)])
        return suggestions[:3]
    except Exception:
        return ["List products", "Check pricing", "How to book"]
    
async def aget_rag_answer_with_agent(business_id, query, chat_history=None):
    try:
        # Better lookup for production (handling potential type mismatches)
        if str(business_id).isdigit():
            biz = await sync_to_async(Business.objects.filter(id=int(business_id)).first)()
        else:
            biz = await sync_to_async(Business.objects.filter(external_uuid=business_id).first)()
            
        if not biz:
            return f"Business ID {business_id} not found in the database. Please check your URL."
    except Exception as e: 
        return f"Database Error: {str(e)}"

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
    
    # Automated Summarization & Windowing (The Production Solution)
    summary = await asummarize_chat_history(chat_history)
    
    summary_text = f"\nLONG-TERM MEMORY (SUMMARY of past events):\n{summary}\n" if summary else ""
    
    system_prompt = f"""
    You are the 'AI Receptionist' for {biz.name}. You are professional, empathetic, and direct.
    {summary_text}
    CORE MEMORY & IDENTITY (STRICT):
    - ALWAYS analyze the 'LONG-TERM MEMORY' (if present) and the 'RECENT MESSAGES' below before answering.
    - If the user has EVER mentioned their name, email, or a business preference, YOU MUST REMEMBER IT.
    - If a user asks "Who am I?" or "Do you know me?", scan all provided context and answer based on facts.
    - Never say "I don't have access to personal information" if the information exists in history.
    - Do not ask for Name or Email if it was already provided.

    TASK 1: Corrective RAG (CRAG) Strategy
    - Step 1: Search docs or website.
    - Step 2: Validate. If local data is weak/missing, YOU must use 'web_search'.
    - Display results as a list with Name, Price, Image, and Link.

    Current Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    
    messages = [SystemMessage(content=system_prompt)]
    
    # Windowing: Send ONLY LAST 4 messages back to AI to save tokens
    recent_history = chat_history[-6:] if chat_history else []
    
    if recent_history:
        for msg in recent_history:
            if msg.get('role') == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg.get('role') == 'assistant':
                messages.append(AIMessage(content=msg['content']))
                
    # Do not append the query if it's already the last message in history (saved in view)
    if not recent_history or recent_history[-1]['content'] != query:
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

    suggestions = await agenerate_suggestions(messages[-1].content)
    return messages[-1].content + f"\n\n[SUGGESTIONS] {' | '.join([f'\"{s}\"' for s in suggestions])} [/SUGGESTIONS]"

async def aget_global_rag_answer(query, chat_history=None):
    """
    Agent that works across ALL businesses.
    """
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)
    
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
                        "business_id": {"type": "string"},
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
                "description": "Search the website of a specific business by its ID for products, services, or specific items.",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "business_id": {"type": "string"},
                        "url": {"type": "string"},
                        "query": {"type": "string", "description": "Specific product or service name to look for."}
                    }, 
                    "required": ["business_id", "url", "query"]
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
    
    # Automated Summarization & Windowing
    summary = await asummarize_chat_history(chat_history)
    summary_text = f"\nLONG-TERM MEMORY (SUMMARY of past events):\n{summary}\n" if summary else ""

    system_prompt = f"""
    You are 'Multi-Business AI Discovery'. You are professional, empathetic, and direct.
    {summary_text}
    GUIDELINES (STRICT & MANDATORY):
    1. INITIALIZATION: You MUST ALWAYS use the 'search_across_businesses' tool with query='list all' to get the real directory. 
    2. NEVER HALLUCINATE: Never make up business names like 'Powerhouse Gym' or 'Dream 11'. Only use data from tools.
    3. FORMATTING (CRITICAL): List businesses EXACTLY like this: "- **[Main Service/Description]** — [Business Name]".
    4. NO NUMBERS: Do not use numbered lists (1, 2, 3). Use bullet points (-).
    5. NO PROVIDED BY: Never use the words "provided by". Use the dash "—".
    6. PROACTIVE: Immediately use tools if the user mentions a service or name.

    6. HANDOFF: Provide direct links to business receptionists:
       [Connect with AI Receptionist](https://ai-reservation.onrender.com/receptionist/[EncodedName]/)

    Current Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """

    messages = [SystemMessage(content=system_prompt)]
    
    # Windowing: More generous 12 message history
    recent_history = chat_history[-12:] if chat_history else []
    
    if recent_history:
        for msg in recent_history:
            if msg.get('role') == 'user':
                messages.append(HumanMessage(content=msg['content']))
            elif msg.get('role') == 'assistant':
                messages.append(AIMessage(content=msg['content']))

    # Append current query
    if not recent_history or recent_history[-1]['content'] != query:
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

    suggestions = await agenerate_suggestions(messages[-1].content)
    return messages[-1].content + f"\n\n[SUGGESTIONS] {' | '.join([f'\"{s}\"' for s in suggestions])} [/SUGGESTIONS]"

def get_rag_answer_with_agent(business_id, query, chat_history=None):
    import asyncio
    return asyncio.run(aget_rag_answer_with_agent(business_id, query, chat_history))
