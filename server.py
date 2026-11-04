import subprocess
import uuid
from mcp.server.mcpserver import MCPServer

mcp=MCPServer("sandbox")

@mcp.tool()
def multiply(a: int,b: int)-> int:
    """Multiply two numbers and return the product."""
    return a*b

@mcp.tool()
def run_code(code: str)->str:
    """Run the python code in an isolated container with no access to network and return the output"""
    name="sandbox"+uuid.uuid4().hex[:8]
    try:
        result=subprocess.run(
            ["docker","run","--rm","--network","none","--user","1234:5678",
            "--read-only","--tmpfs", "/work:rw,size=64m,noexec,nosuid,mode=1777",
            "--workdir", "/work",
            "--cap-drop","ALL", "--security-opt","no-new-privileges",
            "--memory","256m","--memory-swap","256m",
            "--cpus","0.5",
            "--pids-limit","64", "--name", name,
            "-i","python:3.12-slim","python","-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker","kill",name],capture_output=True)    
        return "timed out after 10 seconds"
    out = result.stdout + result.stderr
    if len(out) > 64_000:
        out = out[:64_000] + "\n[output cut at 64 KB]"
    return out
                          
    


if __name__== "__main__":
    mcp.run()