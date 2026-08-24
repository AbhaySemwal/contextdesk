import datetime
import logging
import sys
from mcp.server import MCPServer

# Configure logging to write to stderr so we do not disrupt stdio transport
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("contextdesk-mcp")

# Initialize the MCP Server
server = MCPServer("ContextDesk Tools")

@server.tool()
def get_current_time() -> str:
    """Returns the current local date and time."""
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")

@server.tool()
def calculate(a: float, b: float, operation: str) -> float:
    """Performs arithmetic operations.

    Args:
        a: The first number.
        b: The second number.
        operation: The operation to perform ('add', 'subtract', 'multiply', 'divide').
    """
    op = operation.strip().lower()
    if op == "add":
        return a + b
    elif op == "subtract":
        return a - b
    elif op == "multiply":
        return a * b
    elif op == "divide":
        if b == 0:
            raise ValueError("Error: Division by zero is not allowed.")
        return a / b
    else:
        raise ValueError(
            f"Error: Unsupported operation '{operation}'. Supported operations: add, subtract, multiply, divide."
        )

@server.tool()
def get_project_info() -> dict:
    """Returns basic information about the ContextDesk project, including its name, purpose, and technologies."""
    return {
        "project_name": "ContextDesk",
        "purpose": "A context-aware workspace assistant and tool suite.",
        "technologies": [
            "Python",
            "FastAPI",
            "Uvicorn",
            "Model Context Protocol (MCP)",
            "Google GenAI SDK"
        ]
    }

if __name__ == "__main__":
    # Run the server using stdio transport (default)
    server.run(transport="stdio")
