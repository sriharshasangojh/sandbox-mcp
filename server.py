import subprocess
import uuid
from mcp.server.mcpserver import MCPServer
import time
import re
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



LOCKS = [
    "--network", "none", "--user", "1234:5678",
    "--read-only", "--tmpfs", "/work:rw,size=64m,noexec,nosuid,mode=1777",
    "--workdir", "/work",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
    "--memory", "256m", "--memory-swap", "256m",
    "--cpus", "0.5",
    "--ulimit", "nofile=64:64",
    "--pids-limit", "64",
]



@mcp.tool()
def create_session():
    """start a long-lived sandox that will return session id to pass it onto run_code"""
    session_id=uuid.uuid4().hex[:8]
    name="sbx"+session_id
    result=subprocess.run(
        ["docker","run","-d","--rm","--name",name,"--label","sandbox=1",*LOCKS,"python:3.12-slim","sleep","infinity"],
        capture_output=True,text=True
    )
    if result.returncode != 0:
        return "Could not start session: " + result.stderr
    return session_id



@mcp.tool()
def destroy_session(session_id:str):
    """destroy the container based on the session id given in input"""
    if session_id:
        if not re.fullmatch(r"[0-9a-f]{8}", session_id):
            return "invalid session_id"
        container="sbx"+session_id 
        result=subprocess.run(["docker","kill",container],capture_output=True,text=True)  

        if result.returncode !=0:
            return "session not found"
        return "session destroyed"     

@mcp.tool()
def run_code(code: str,session_id: str = "")->str:
    """Run the python code in an isolated container with no access to network and return the output"""
    started=time.time()
    if too_many():
        save_db(started,code,"rate_limited",None,"")
        return "Too many runs. Wait a minute before trying again"

    if session_id:
        if not re.fullmatch(r"[0-9a-f]{8}", session_id):
            return "invalid session_id"
        container="sbx"+session_id
        cmd=["docker","exec","-i", container, "timeout", "10", "python", "-"]  
        wait=15

    else:
        container="sandbox"+uuid.uuid4().hex[:8]
        cmd=["docker","run", "--rm", *LOCKS, "--name",container,"-i", "python:3.12-slim", "python", "-"]     
        wait=10
    try:
        result=subprocess.run(
            cmd,
            input=code,
            capture_output=True,
            text=True,
            timeout=wait,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker","kill",container],capture_output=True)  
        save_db(started,code, "timeout", None, "")  
        return "timed out after 10 seconds"

    if session_id and "No such container" in result.stderr:
        return "Session not found or expired. Call create_session to start a new one."    

    out = result.stdout + result.stderr
    if len(out) > 64_000:
        out = out[:64_000] + "\n[output cut at 64 KB]"
    if result.returncode == 0:
        status = "ok"
    elif result.returncode == 124:
       status = "timeout"    
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