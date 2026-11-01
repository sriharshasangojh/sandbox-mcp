from mcp.server.mcpserver import MCPServer

mcp=MCPServer("sandbox")

@mcp.tool()
def multiply(a: int,b: int)-> int:
    """Multiply two numbers and return the product."""
    return a*b


if __name__== "__main__":
    mcp.run()