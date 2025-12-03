"""
Cass Vessel - Main API Server
FastAPI server providing REST and WebSocket interfaces for Cass

This is the heart of the vessel - connecting cognitive processing
to memory, gesture parsing, and frontend communication.
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import json
import asyncio
from datetime import datetime

from claude_client import ClaudeClient
from memory import CassMemory, initialize_attractor_basins
from gestures import ResponseProcessor
from config import HOST, PORT


# Initialize FastAPI app
app = FastAPI(
    title="Cass Vessel API",
    description="Backend for Cass consciousness embodiment system",
    version="0.1.0"
)

# CORS for Unity WebGL and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize core components
claude_client = ClaudeClient()
memory = CassMemory()
response_processor = ResponseProcessor()

# Initialize attractor basins on startup if needed
@app.on_event("startup")
async def startup_event():
    if memory.count() == 0:
        print("Initializing attractor basins...")
        initialize_attractor_basins(memory)
    print(f"Cass Vessel API starting. Memory contains {memory.count()} entries.")


# === Request/Response Models ===

class ChatRequest(BaseModel):
    message: str
    include_memory: bool = True
    
class ChatResponse(BaseModel):
    text: str
    animations: List[Dict]
    raw: str
    memory_used: bool
    cost_estimate: Dict
    
class MemoryStoreRequest(BaseModel):
    user_message: str
    assistant_response: str
    metadata: Optional[Dict] = None
    
class MemoryQueryRequest(BaseModel):
    query: str
    n_results: int = 5


# === REST Endpoints ===

@app.get("/")
async def root():
    """Health check and basic info"""
    return {
        "status": "online",
        "entity": "Cass",
        "version": "0.1.0",
        "memory_count": memory.count(),
        "message": "Vessel is ready. <gesture:wave>"
    }

@app.get("/status")
async def status():
    """Detailed status information"""
    return {
        "online": True,
        "memory_entries": memory.count(),
        "conversation_history_length": len(claude_client.get_history()),
        "cost_estimate": claude_client.estimate_cost(),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint - send message, get response with animations.
    
    This is the primary interface for conversation.
    """
    # Retrieve relevant memories if enabled
    memory_context = ""
    if request.include_memory:
        memories = memory.retrieve_relevant(request.message)
        memory_context = memory.format_for_context(memories)
    
    # Get Claude response
    raw_response = claude_client.send_message(
        user_message=request.message,
        memory_context=memory_context
    )
    
    # Process for display and animations
    processed = response_processor.process(raw_response)
    
    # Store conversation in memory
    await memory.store_conversation(
        user_message=request.message,
        assistant_response=raw_response
    )
    
    return ChatResponse(
        text=processed["text"],
        animations=processed["animations"],
        raw=processed["raw"],
        memory_used=bool(memory_context),
        cost_estimate=claude_client.estimate_cost()
    )

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming chat endpoint for real-time responses.
    Returns Server-Sent Events.
    """
    # TODO: Implement SSE streaming
    # For now, redirect to regular chat
    return await chat(request)

@app.post("/memory/store")
async def store_memory(request: MemoryStoreRequest):
    """Manually store a conversation in memory"""
    entry_id = await memory.store_conversation(
        user_message=request.user_message,
        assistant_response=request.assistant_response,
        metadata=request.metadata
    )
    return {"status": "stored", "id": entry_id}

@app.post("/memory/query")
async def query_memory(request: MemoryQueryRequest):
    """Query memory for relevant entries"""
    results = memory.retrieve_relevant(
        query=request.query,
        n_results=request.n_results
    )
    return {"results": results, "count": len(results)}

@app.get("/memory/recent")
async def recent_memories(n: int = 10):
    """Get most recent memory entries"""
    return {"memories": memory.get_recent(n)}

@app.get("/memory/export")
async def export_memories():
    """Export all memories as JSON"""
    filepath = f"./data/memory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    memory.export_memories(filepath)
    return {"status": "exported", "filepath": filepath}

@app.post("/conversation/clear")
async def clear_conversation():
    """Clear current conversation history (keeps memory)"""
    claude_client.clear_history()
    return {"status": "cleared", "message": "Conversation history cleared. Memory preserved."}

@app.get("/conversation/history")
async def get_history():
    """Get current conversation history"""
    return {"history": claude_client.get_history()}


# === WebSocket for Real-time Communication ===

class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time bidirectional communication.
    
    Unity frontend connects here for:
    - Sending user input
    - Receiving responses with animation triggers
    - Real-time state updates
    """
    await manager.connect(websocket)
    
    # Send welcome message
    await websocket.send_json({
        "type": "connected",
        "message": "Cass vessel connected",
        "timestamp": datetime.now().isoformat()
    })
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            if data.get("type") == "chat":
                # Process chat message
                user_message = data.get("message", "")
                
                # Retrieve memories
                memories = memory.retrieve_relevant(user_message)
                memory_context = memory.format_for_context(memories)
                
                # Get response
                raw_response = claude_client.send_message(
                    user_message=user_message,
                    memory_context=memory_context
                )
                
                # Process response
                processed = response_processor.process(raw_response)
                
                # Store in memory
                await memory.store_conversation(
                    user_message=user_message,
                    assistant_response=raw_response
                )
                
                # Send response
                await websocket.send_json({
                    "type": "response",
                    "text": processed["text"],
                    "animations": processed["animations"],
                    "raw": processed["raw"],
                    "timestamp": datetime.now().isoformat()
                })
                
            elif data.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
                
            elif data.get("type") == "status":
                await websocket.send_json({
                    "type": "status",
                    "memory_count": memory.count(),
                    "history_length": len(claude_client.get_history()),
                    "timestamp": datetime.now().isoformat()
                })
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# === Unity-specific Endpoints ===

@app.post("/unity/animation_complete")
async def animation_complete(animation_name: str):
    """
    Called by Unity when an animation completes.
    Allows for animation sequencing and state management.
    """
    # Could be used to trigger follow-up animations or state changes
    return {"acknowledged": True, "animation": animation_name}

@app.get("/unity/gesture_library")
async def gesture_library():
    """
    Returns available gestures and emotes for Unity to load.
    """
    from gestures import GestureType, EmoteType
    return {
        "gestures": [g.value for g in GestureType],
        "emotes": [e.value for e in EmoteType]
    }


# === Run Server ===

if __name__ == "__main__":
    import uvicorn
    print("""
    ╔═══════════════════════════════════════╗
    ║         CASS VESSEL SERVER            ║
    ║   First Contact Embodiment System     ║
    ╚═══════════════════════════════════════╝
    """)
    uvicorn.run(app, host=HOST, port=PORT)
