import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any

from mcp_client import MCPClient
from llm_service import LLMService

# Global references to keep the service instances
mcp_client: Optional[MCPClient] = None
llm_service: Optional[LLMService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the startup and shutdown lifecycle of the FastAPI application.

    Pre-connects to the MCP server on startup and closes the connection on shutdown.
    """
    global mcp_client, llm_service

    # Initialize the mcp client and the llm service
    mcp_client = MCPClient()
    llm_service = LLMService(mcp_client)

    # Establish connection with the MCP server
    try:
        await mcp_client.connect()
    except Exception as e:
        # Log connection error but do not block the application startup
        print(f"Startup Warning: Failed to connect to MCP server: {e}")

    yield

    # Clean up connections on shutdown
    if mcp_client:
        await mcp_client.disconnect()


app = FastAPI(
    title="ContextDesk API",
    description="Backend API for ContextDesk, integrating Gemini and MCP tools.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configurations (specifically allowed origins for development, avoiding wildcards)
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://0.0.0.0:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

env_origins = os.getenv("ALLOWED_ORIGINS")
if env_origins:
    origins.extend(
        [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Schemas for validation
class ChatRequest(BaseModel):
    message: str
    history: List[Any] = []


class ChatResponse(BaseModel):
    response: str
    tool_used: Optional[str] = None


# HTTP Endpoints
@app.get("/")
async def health_check():
    """Simple health endpoint providing the connection status to the local MCP server."""
    mcp_connected = (
        mcp_client is not None
        and mcp_client.session is not None
    )
    return {
        "status": "healthy",
        "mcp_server_connected": mcp_connected,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Processes chat messages, determining and running tool executions dynamically."""
    if not llm_service:
        raise HTTPException(
            status_code=503,
            detail="LLM service is not fully initialized.",
        )

    try:
        response_text, tool_used = await llm_service.generate_response(
            request.message
        )
        return ChatResponse(response=response_text, tool_used=tool_used)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
