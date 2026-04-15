import json
import asyncio
import os
import websockets
from channels.generic.websocket import AsyncWebsocketConsumer
from external_db_handler import check_availability, create_booking_ext

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
VOICE = 'alloy'

# System Prompt
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

class VoiceReceptionistConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        print("======== [CONSUMER CONNECTED] ========")
        print(f"Path: {self.scope.get('path')}")
        
        if not OPENAI_API_KEY:
            msg = "[ERROR] OPENAI_API_KEY not found in environment variables."
            print(msg)
            await self.send(json.dumps({"event": "error", "message": msg}))
            await self.close()
            return

        self.browser_queue = asyncio.Queue()
        self.openai_ws = None
        
        try:
            print(f"Connecting to OpenAI Realtime API (Key length: {len(OPENAI_API_KEY) if OPENAI_API_KEY else 0})...")
            self.openai_ws = await websockets.connect(
                'wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17',
                extra_headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1"
                }
            )
            print("[OK] Connected to OpenAI Realtime")
            await self.initialize_session()
            print("[OK] Session initialized and ready")

            # Start the main coordination loop
            self.loop_task = asyncio.create_task(self.run_main_loop())
            
        except Exception as e:
            print(f"[ERROR] Failed to connect to OpenAI: {e}")
            await self.send(json.dumps({"event": "error", "message": f"OpenAI connect failed: {str(e)}"}))
            await self.close()

    async def disconnect(self, close_code):
        print(f"Browser disconnected, close_code={close_code}")
        if hasattr(self, 'loop_task'):
            self.loop_task.cancel()
        if hasattr(self, 'openai_ws') and self.openai_ws:
            await self.openai_ws.close()

    async def receive(self, text_data):
        """Put messages from the browser into a queue."""
        await self.browser_queue.put(text_data)

    async def run_main_loop(self):
        """Coordinate simultaneous tasks using asyncio.wait."""
        t1 = asyncio.create_task(self.forward_browser_to_openai())
        t2 = asyncio.create_task(self.forward_openai_to_browser())
        
        try:
            done, pending = await asyncio.wait(
                [t1, t2],
                return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()
        except Exception as e:
            print(f"Main loop error: {e}")
        finally:
            await self.close()

    async def forward_browser_to_openai(self):
        """Forward audio/events from browser queue to OpenAI."""
        try:
            while True:
                message = await self.browser_queue.get()
                data = json.loads(message)
                if data.get('event') == 'media':
                    audio_event = {
                        "type": "input_audio_buffer.append",
                        "audio": data['media']['payload']
                    }
                    await self.openai_ws.send(json.dumps(audio_event))
        except Exception as e:
            print(f"forward_browser_to_openai error: {e}")

    async def forward_openai_to_browser(self):
        """Forward audio/events from OpenAI to browser, handle tool calls."""
        try:
            async for message in self.openai_ws:
                response = json.loads(message)
                event_type = response.get('type')

                # Log useful info
                if event_type == 'input_audio_buffer.speech_started':
                    print("\n==> User started speaking...")
                elif event_type == 'conversation.item.input_audio_transcription.completed':
                    print(f"USER SAID: {response.get('transcript')}")
                elif event_type == 'response.done':
                    print("\n[AI Finished Response]")

                # Forward audio delta
                if event_type == 'response.audio.delta' and response.get('delta'):
                    await self.send(json.dumps({
                        "event": "media",
                        "media": {"payload": response['delta']}
                    }))

                # Handle tool calls
                elif event_type == 'response.done':
                    output = response.get('response', {}).get('output', [])
                    for item in output:
                        if item.get('type') == 'function_call':
                            await self.handle_tool_call(item)

                elif event_type == 'error':
                    err = response.get('error', {})
                    print(f"OpenAI error: {err}")
                    await self.send(json.dumps({"event": "error", "message": str(err)}))

        except Exception as e:
            print(f"forward_openai_to_browser error: {e}")

    async def initialize_session(self):

        """First session update to set tools and instructions."""
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
                                "service": {"type": "string", "description": "Name of the service"},
                                "time": {"type": "string", "description": "Requested time in ISO format (e.g. 2026-04-15T10:00:00Z)"}
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
        await self.openai_ws.send(json.dumps(session_update))

        # Initial greeting
        greet_event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello"}]
            }
        }
        await self.openai_ws.send(json.dumps(greet_event))
        await self.openai_ws.send(json.dumps({"type": "response.create"}))

    async def handle_tool_call(self, tool_call):
        """Execute function calls from OpenAI."""
        name = tool_call['name']
        args = json.loads(tool_call['arguments'])
        call_id = tool_call['call_id']

        print(f"Tool called: {name} | Args: {args}")

        try:
            if name == 'check_availability':
                # Run blocking DB call in thread
                result = await asyncio.to_thread(check_availability, args['service'], args['time'])
            elif name == 'create_booking':
                result = await asyncio.to_thread(
                    create_booking_ext,
                    args['service'],
                    args['time'],
                    args['name'],
                    args['phone'],
                    args.get('notes', '')
                )
            else:
                result = {"error": "Unknown tool"}
            
            print(f"Tool result: {result}")
        except Exception as e:
            print(f"[ERROR] Tool execution failed: {e}")
            result = {"error": str(e)}

        # Send result back
        tool_response = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result)
            }
        }
        await self.openai_ws.send(json.dumps(tool_response))
        await self.openai_ws.send(json.dumps({"type": "response.create"}))
