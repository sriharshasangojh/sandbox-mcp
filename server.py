import subprocess
from mcp.server.mcpserver import MCPServer

mcp=MCPServer("sandbox")

@mcp.tool()
def multiply(a: int,b: int)-> int:
    """Multiply two numbers and return the product."""
    return a*b

@mcp.tool()
def run_code(code: str)->str:
    """Run the python code in an isolated container with no access to network and return the output"""
    result=subprocess.run(
        ["docker","run","--rm","--network","none","--user","1234:5678",
        "--read-only","--tmpfs", "/work:rw,size=64m,mode=1777",
        "--workdir", "/work",
        "--cap-drop","ALL", "--security-opt","no-new-privileges","-i","python:3.12-slim","python","-"],
        input=code,
        capture_output=True,
        text=True,
    )
    return result.stdout+result.stderr
                          
    


if __name__== "__main__":
    mcp.run()