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

def save_db(started, code, status, exit_code, output):
    with sqlite3.connect(DB) as db:
        db.execute(
            "INSERT INTO jobs (created_at,code,status,exit_code,output,duration_ms)"
            "VALUES (?, ?, ?, ?, ?, ?)",(started,code,status,exit_code,output,int((time.time()-started)*1000)),
        )

mcp=MCPServer("sandbox")

@mcp.tool()
def multiply(a: int,b: int)-> int:
    """Multiply two numbers and return the product."""
    return a*b

@mcp.tool()
def run_code(code: str)->str:
    """Run the python code in an isolated container with no access to network and return the output"""
    name="sandbox"+uuid.uuid4().hex[:8]
    started=time.time()
    if too_many():
        save_db(started,code,"rate_limited",None,"")
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
        save_db(started,code, "timeout", None, "")  
        return "timed out after 10 seconds"
    out = result.stdout + result.stderr
    if len(out) > 64_000:
        out = out[:64_000] + "\n[output cut at 64 KB]"
    if result.returncode == 0:
        status = "ok"
    elif result.returncode == 137:
        status = "killed"
    else:
        status = "error"
    save_db(started,code, status, result.returncode, out)
    return out
                    
@mcp.tool()
def list_jobs(limit: int = 10) -> str:
    """List the most recent code runs: id, status, exit code and duration."""
    limit = min(limit, 50)          # never return more than 50 rows
    with sqlite3.connect(DB) as db:
        rows = db.execute(
            "SELECT id, status, exit_code, duration_ms FROM jobs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    if not rows:
        return "No jobs yet."
    return "\n".join(f"#{r[0]} {r[1]} exit={r[2]} {r[3]}ms" for r in rows)   

@mcp.tool()
def get_job(job_id:int)->str:
    """Get the row from jobs.db database based on the passed job id"""
    with sqlite3.connect(DB) as db:
        row=db.execute(
            "SELECT id, status, exit_code, duration_ms FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
    if not row:
        return "No job with job_id exists in jobs"
    return f"#{row[0]} {row[1]} exit={row[2]} {row[3]}ms"


if __name__== "__main__":
    mcp.run()