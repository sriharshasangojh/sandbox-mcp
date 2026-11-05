import subprocess
import uuid
from mcp.server.mcpserver import MCPServer
import time
from collections import deque
import sqlite3, os

import threading
limit = threading.BoundedSemaphore(3)

calls=deque()
MAX_CALLS,WINDOW=10,60

def too_many():
    now=time.time()
    while calls and now-calls[0]>WINDOW:
        calls.popleft()
    if len(calls)>=MAX_CALLS:
        return True
    calls.append(now)
    return False        


DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs.db")
 
def init_db():
    with sqlite3.connect(DB) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at REAL,
        code TEXT,
        status TEXT,
        exit_code INTEGER,
        output TEXT,
        duration_ms INTEGER
        )""")


init_db()

mcp=MCPServer("sandbox")

@mcp.tool()
def multiply(a: int,b: int)-> int:
    """Multiply two numbers and return the product."""
    return a*b

@mcp.tool()
def run_code(code: str)->str:
    """Run the python code in an isolated container with no access to network and return the output"""
    name="sandbox"+uuid.uuid4().hex[:8]
    if too_many():
        return "Too many runs. Wait a minute before trying again"
    try:
        result=subprocess.run(
            ["docker","run","--rm","--network","none","--user","1234:5678",
            "--read-only","--tmpfs", "/work:rw,size=64m,noexec,nosuid,mode=1777",
            "--workdir", "/work",
            "--cap-drop","ALL", "--security-opt","no-new-privileges",
            "--memory","256m","--memory-swap","256m",
            "--cpus","0.5",
            "--ulimit", "nofile=64:64",
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