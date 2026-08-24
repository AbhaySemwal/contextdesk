import logging
import os
from typing import Optional, Tuple
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp_client import MCPClient

# Configure logging
logger = logging.getLogger("contextdesk-llm-service")


class LLMService:
    """Manages Gemini LLM requests and dynamic integration with the local MCP server."""

    def __init__(self, mcp_client: MCPClient):
        # Load environment variables from the backend directory
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dotenv_path = os.path.join(base_dir, "backend", ".env")
        load_dotenv(dotenv_path=dotenv_path)
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        # Never expose API key in logs or error messages
        if not self.api_key:
            raise ValueError(
                "Gemini configuration error: GEMINI_API_KEY environment variable is missing."
            )

        self.mcp_client = mcp_client
        # Initialize Google GenAI client (api_key is kept private inside client)
        self.client = genai.Client(api_key=self.api_key)

    async def generate_response(self, user_message: str) -> Tuple[str, Optional[str]]:
        """Generates a natural language response, invoking MCP tools dynamically if required.

        Returns:
            A tuple of (response_text, tool_used_name_or_None).
        """
        # 1. Establish connection to the local MCP server if not already connected
        try:
            await self.mcp_client.connect()
        except Exception as e:
            logger.error(
                f"Graceful handle: Failed to connect to MCP server. Proceeding without tools. Detail: {e}"
            )

        # 2. Retrieve available MCP tools
        mcp_tools = []
        if self.mcp_client.session is not None:
            try:
                mcp_tools = await self.mcp_client.list_tools()
            except Exception as e:
                logger.error(
                    f"Graceful handle: Failed to list tools from MCP server. Detail: {e}"
                )

        # 3. Map MCP tool definitions to Gemini FunctionDeclarations
        gemini_tools = []
        for tool in mcp_tools:
            try:
                input_schema = tool.input_schema or {}
                # Parse tool's input schema to types.Schema
                schema = types.Schema.model_validate(input_schema)

                decl = types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=schema,
                )
                gemini_tools.append(decl)
            except Exception as e:
                logger.warning(
                    f"Failed to parse schema for tool '{tool.name}': {e}. Skipping tool."
                )

        # 4. Generate first turn content to decide if a tool call is required
        config = types.GenerateContentConfig()
        if gemini_tools:
            config.tools = [types.Tool(function_declarations=gemini_tools)]
            config.automatic_function_calling = types.AutomaticFunctionCallingConfig(disable=True)

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name, contents=user_message, config=config
            )
        except Exception as e:
            logger.error(f"GenAI generate_content request failed: {e}")
            raise RuntimeError("Failed to generate content from Gemini LLM.") from e

        # 5. Check if the LLM decided to execute a tool
        tool_used = None
        tool_result_context = ""

        if response.function_calls:
            func_call = response.function_calls[0]
            tool_used = func_call.name
            args = func_call.args or {}

            # Handle malformed LLM tool decisions (e.g. unknown tool name)
            available_tool_names = {t.name for t in mcp_tools}
            if tool_used not in available_tool_names:
                logger.warning(
                    f"LLM decided to call unknown/unregistered tool: '{tool_used}'"
                )
                tool_result_context = (
                    f"Error: Tool '{tool_used}' is not available on this workspace."
                )
            else:
                # 6. Execute the tool through the MCP client
                logger.info(f"Calling MCP Tool '{tool_used}' with arguments: {args}")
                try:
                    tool_res = await self.mcp_client.call_tool(tool_used, args)

                    # Extract result text safely
                    if hasattr(tool_res, "content") and tool_res.content:
                        tool_result_context = "\n".join(
                            c.text for c in tool_res.content if hasattr(c, "text")
                        )
                    else:
                        tool_result_context = str(tool_res)

                except Exception as e:
                    # Handle MCP and tool errors gracefully
                    logger.error(f"Graceful handle: MCP tool execution failed: {e}")
                    tool_result_context = (
                        f"Error encountered while executing tool '{tool_used}': {e}"
                    )

        # 7. Synthesize final response if a tool was executed
        if tool_used:
            # We feed the tool's output back to the LLM to write the final natural language answer
            second_prompt = f"""
User query: {user_message}

The workspace executed the tool '{tool_used}' and retrieved the following result/status:
{tool_result_context}

Please synthesize a final, user-friendly natural language response based on this result.
"""
            try:
                # Call without tools parameter to prevent infinite loop / recursion
                final_response = await self.client.aio.models.generate_content(
                    model=self.model_name, contents=second_prompt
                )
                return final_response.text or "", tool_used
            except Exception as e:
                logger.error(f"GenAI second-turn synthesis failed: {e}")
                # Fallback directly to raw result representation
                return (
                    f"Here is the tool output for '{tool_used}':\n{tool_result_context}",
                    tool_used,
                )

        # No tool was called; return the first turn response directly
        return response.text or "", None
