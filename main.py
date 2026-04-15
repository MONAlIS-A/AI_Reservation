import os
import sys
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
import websockets

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))

SYSTEM_MESSAGE = (
    "You are a professional, warm and friendly AI Receptionist. "
    "Your job is to help customers book appointments for services. "
    "Here are the ONLY available services you can book: 'Teeth Cleaning', 'Whitening', 'Gym', 'Calistenic', 'doom'. "
    "Do NOT assume or make up service names. Always map the customer's request to one of these exact services. "
    "To book an appointment: "
    "1. First, always call 'check_availability' to check if the requested slot is free. "
    "2. If the slot is not available, tell the customer the next available slot from the tool result and ask if they want to book that. "
    "3. If the slot is available, collect customer name and phone number, then call 'create_booking'. "
    "4. Always confirm the booking details back to the customer. "
    f"Today's date is April 15, 2026. "
    "You can speak both in English and Bengali depending on the customer's preference. "
    "Be conversational and natural, like a real human receptionist."
)

VOICE = 'alloy'

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError('Missing the OPENAI_API_KEY environment variable.')

# Serve static HTML
@app.get("/", response_class=HTMLResponse)
async def index_page():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.websocket("/browser-stream")
async def browser_stream(websocket: WebSocket):
    """Direct browser to OpenAI Realtime WebSocket (no Twilio needed)."""
    await websocket.accept()
    print("Browser client connected")

    openai_ws = None
    try:
        print("Connecting to OpenAI Realtime API...")
        openai_ws = await websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        )
        print("[OK] Connected to OpenAI Realtime")
        await initialize_session(openai_ws)
        print("[OK] Session initialized")

        async def receive_from_browser():
            """Forward audio from browser to OpenAI."""
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data.get('event') == 'media':
                        audio_event = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_event))
            except WebSocketDisconnect:
                print("Browser disconnected")
            except Exception as e:
                print(f"receive_from_browser error: {e}")

        async def receive_from_openai():
            """Forward audio from OpenAI to browser, handle tool calls."""
            try:
                async for message in openai_ws:
                    response = json.loads(message)
                    event_type = response.get('type')
                    
                    # Print useful debug messages instead of every event
                    if event_type == 'input_audio_buffer.speech_started':
                        print("\n==> User started speaking...")
                    elif event_type == 'input_audio_buffer.speech_stopped':
                        print("==> User stopped speaking.")
                    elif event_type == 'conversation.item.input_audio_transcription.completed':
                        print(f"USER SAID: {response.get('transcript')}")
                    elif event_type == 'response.audio_transcript.delta':
                        print(response.get('delta', ''), end='', flush=True)
                    elif event_type == 'response.done':
                        print("\n[AI Finished Response]")

                    if event_type == 'response.audio.delta' and response.get('delta'):
                        try:
                            await websocket.send_json({
                                "event": "media",
                                "media": {"payload": response['delta']}
                            })
                        except Exception as e:
                            print(f"Audio send error: {e}")

                    elif event_type == 'response.done':
                        output = response.get('response', {}).get('output', [])
                        for item in output:
                            if item.get('type') == 'function_call':
                                await handle_tool_call(openai_ws, item)

                    elif event_type == 'error':
                        err = response.get('error', {})
                        print(f"OpenAI error: {err}")
                        try:
                            await websocket.send_json({
                                "event": "error",
                                "message": str(err)
                            })
                        except:
                            pass

            except Exception as e:
                print(f"receive_from_openai error: {e}")
            print("receive_from_openai task completely finished.")

        t1 = asyncio.create_task(receive_from_browser())
        t2 = asyncio.create_task(receive_from_openai())
        
        done, pending = await asyncio.wait(
            [t1, t2],
            return_when=asyncio.FIRST_COMPLETED
        )
        for p in pending:
            p.cancel()

    except Exception as e:
        print(f"[ERROR] browser_stream: {type(e).__name__}: {e}")
        try:
            await websocket.send_json({"event": "error", "message": str(e)})
        except:
            pass
    finally:
        print("Session ended")
        if openai_ws:
            try:
                await openai_ws.close()
            except:
                pass


async def initialize_session(openai_ws):
    """Initialize OpenAI session with system prompt and tools."""
    session_update = {
        "type": "session.update",
        "session": {
            "instructions": SYSTEM_MESSAGE,
            "voice": VOICE,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            "modalities": ["text", "audio"],
            "temperature": 0.7,
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.8,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 1000,
                "create_response": True
            },
            "tools": [
                {
                    "type": "function",
                    "name": "check_availability",
                    "description": "Check if a time slot is available for a service before booking.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service": {"type": "string", "description": "Name of the service (e.g., 'Dental Checkup', 'General Consultation')"},
                            "time": {"type": "string", "description": "Requested appointment time in ISO format e.g. 2026-04-15T10:00:00Z"}
                        },
                        "required": ["service", "time"]
                    }
                },
                {
                    "type": "function",
                    "name": "create_booking",
                    "description": "Create a confirmed booking after availability is confirmed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Customer full name"},
                            "phone": {"type": "string", "description": "Customer phone number"},
                            "service": {"type": "string", "description": "Service name"},
                            "time": {"type": "string", "description": "ISO format appointment time"},
                            "notes": {"type": "string", "description": "Any additional notes"}
                        },
                        "required": ["name", "phone", "service", "time"]
                    }
                }
            ],
            "tool_choice": "auto"
        }
    }
    await openai_ws.send(json.dumps(session_update))

    # Greet the customer immediately
    await openai_ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Hello"}]
        }
    }))
    await openai_ws.send(json.dumps({"type": "response.create"}))


async def handle_tool_call(openai_ws, tool_call):
    """Execute function calls requested by OpenAI."""
    from external_db_handler import check_availability, create_booking_ext

    name = tool_call['name']
    args = json.loads(tool_call['arguments'])
    call_id = tool_call['call_id']

    print(f"Tool called: {name} | Args: {args}")

    if name == 'check_availability':
        try:
            result = check_availability(args['service'], args['time'])
        except Exception as e:
            result = {"error": str(e)}

    elif name == 'create_booking':
        try:
            result = create_booking_ext(
                args['service'],
                args['time'],
                args['name'],
                args['phone'],
                args.get('notes', '')
            )
        except Exception as e:
            result = {"status": "error", "message": str(e)}
    else:
        result = {"error": "Unknown tool"}

    # Send result back to OpenAI
    tool_response = {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(result)
        }
    }
    await openai_ws.send(json.dumps(tool_response))
    await openai_ws.send(json.dumps({"type": "response.create"}))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
