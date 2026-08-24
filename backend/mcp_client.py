import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Configure logging
logger = logging.getLogger("contextdesk-mcp-client")

# Locate project base directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SERVER_PATH = os.path.join(BASE_DIR, "mcp_server", "server.py")
DEFAULT_PYTHON_PATH = os.path.join(BASE_DIR, "backend", "venv", "bin", "python")

# Fallback to current sys.executable if virtual environment python isn't found
if not os.path.exists(DEFAULT_PYTHON_PATH):
    DEFAULT_PYTHON_PATH = sys.executable


class MCPClient:
    """An asynchronous MCP client for communicating with a local stdio MCP server."""

    def __init__(
        self,
        server_script_path: str = DEFAULT_SERVER_PATH,
        python_path: str = DEFAULT_PYTHON_PATH,
    ):
        self.server_script_path = server_script_path
        self.python_path = python_path
        self._exit_stack: Optional[AsyncExitStack] = None
        self.session: Optional[ClientSession] = None

    async def connect(self, timeout: float = 10.0) -> None:
        """Establishes connection to the MCP server using Stdio transport."""
        if self.session is not None:
            logger.debug("Already connected to MCP server.")
            return

        logger.info(
            f"Connecting to MCP server via stdio: {self.python_path} {self.server_script_path}"
        )
        self._exit_stack = AsyncExitStack()
        try:
            # Build connection parameters
            server_params = StdioServerParameters(
                command=self.python_path,
                args=[self.server_script_path],
                env=os.environ.copy(),
            )

            # Establish the stdio transport channel
            read_stream, write_stream = await asyncio.wait_for(
                self._exit_stack.enter_async_context(stdio_client(server_params)),
                timeout=timeout,
            )

            # Set up the protocol session
            self.session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            # Perform handshakes and initializations
            await asyncio.wait_for(self.session.initialize(), timeout=timeout)
            logger.info("MCP client connection established and session initialized.")

        except asyncio.TimeoutError as e:
            logger.error("Timeout occurred while connecting/initializing the MCP server.")
            await self.disconnect()
            raise TimeoutError("Connection to MCP server timed out.") from e
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            await self.disconnect()
            raise ConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def disconnect(self) -> None:
        """Closes the session and cleans up connection resources."""
        if self._exit_stack is not None:
            logger.info("Disconnecting from MCP server...")
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                logger.warning(f"Error encountered during disconnect cleanup: {e}")
            finally:
                self._exit_stack = None
                self.session = None
                logger.info("MCP server connection cleaned up.")

    async def list_tools(self, timeout: float = 5.0) -> List[Any]:
        """Lists all tools exposed by the MCP server."""
        if self.session is None:
            raise ConnectionError("Not connected to the MCP server. Call connect() first.")

        try:
            response = await asyncio.wait_for(
                self.session.list_tools(), timeout=timeout
            )
            return response.tools if hasattr(response, "tools") else []
        except asyncio.TimeoutError as e:
            logger.error("List tools request timed out.")
            raise TimeoutError("Request to list tools timed out.") from e
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            raise RuntimeError(f"Failed to list tools: {e}") from e

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any], timeout: float = 10.0
    ) -> Any:
        """Invokes a specific tool on the MCP server with the provided arguments."""
        if self.session is None:
            raise ConnectionError("Not connected to the MCP server. Call connect() first.")

        try:
            # Send the tool call request
            response = await asyncio.wait_for(
                self.session.call_tool(tool_name, arguments=arguments),
                timeout=timeout,
            )

            # Check if the server reported a tool execution failure
            if hasattr(response, "is_error") and response.is_error:
                err_msg = ""
                if hasattr(response, "content") and response.content:
                    err_msg = " ".join(
                        c.text for c in response.content if hasattr(c, "text")
                    )
                raise ValueError(
                    f"MCP Tool Error: {err_msg or 'Unknown server-side error'}"
                )

            return response

        except asyncio.TimeoutError as e:
            logger.error(f"Tool call '{tool_name}' timed out.")
            raise TimeoutError(f"Tool call '{tool_name}' timed out.") from e
        except ValueError as e:
            # Re-raise standard tool execution failures
            raise e
        except Exception as e:
            logger.error(f"Error occurred executing tool '{tool_name}': {e}")
            raise RuntimeError(f"Error occurred executing tool '{tool_name}': {e}") from e

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
