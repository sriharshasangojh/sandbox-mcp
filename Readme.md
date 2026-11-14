# sandbox-mcp

An MCP server that lets an AI run Python code **safely**. Every run happens inside a locked-down,
throwaway Docker container: no network, no root, no way to touch the host, and hard limits on
memory, CPU, processes, disk and time. Every run is logged to SQLite, and the sandbox is checked
by a set of attack tests.

> Demo: https://drive.google.com/file/d/1TRgEg6wPTYwVuA6JDRHz9RksB3qGLI-u/view?usp=sharing

## Why this exists

An AI that can run code is useful, and also risky: the code is written by a model, not reviewed by
a person. `sandbox-mcp` puts a strong boundary around that code, so the worst a bad snippet can do
is waste a few seconds inside a container that is deleted afterwards.

## How it works

```
AI app (Antigravity, Claude, Inspector ...)
        |  MCP over stdio
        v
   server.py   <-- runs on your machine, trusted
        |  docker run / docker exec
        v
   container   <-- only the AI's code runs here, locked down
```

- `server.py` is the trusted part. It validates every input, enforces the limits and talks to Docker.
- The container only ever receives the code string, through standard input. It never talks to MCP,
  and it has no network.
- Tools that need the network or secrets (APIs, SSH) must be separate, fixed tools in `server.py`.
  They never run inside the sandbox.

## Tools

run_many: run up to 5 snippets in parallel (3 at a time), results returned in order

| Tool | What it does |
|---|---|
| `run_code(code, session_id="")` | Run Python in a fresh container, or inside a session if `session_id` is given. |
| `create_session()` | Start a long-lived container. Files in `/work` persist across runs. Returns a session id. |
| `destroy_session(session_id)` | Stop and delete a session. |
| `write_file(session_id, path, content)` | Save a text file into a session's `/work` (path-checked, max 1 MB). |
| `read_file(session_id, path)` | Read a text file from a session's `/work` (output cut at 64 KB). |
| `list_jobs(limit=10)` | Recent runs: id, status, exit code, duration. |
| `get_job(job_id)` | One run from the job log. |

## Locks around the code

**Container locks** (applied to every container):

| Flag | What it stops |
|---|---|
| `--network none` | Any network access: no downloads, no data leaving, no SSH. |
| `--user 1234:5678` | Running as root. |
| `--cap-drop ALL`, `--security-opt no-new-privileges` | Gaining special powers, including through setuid tricks. |
| `--read-only` | Writing anywhere except `/work`. |
| `--tmpfs /work:rw,size=64m,noexec,nosuid` | Filling the disk (64 MB cap), and running programs written into `/work`. |
| `--memory 256m --memory-swap 256m` | Memory bombs. 256 MB hard cap, no swap. |
| `--cpus 0.5` | Hogging the CPU. |
| `--pids-limit 64` | Fork bombs and thread bombs. |
| `--ulimit nofile=64:64` | Opening too many files. |

No `--privileged`, no Docker socket mount, no host folder mounts, no host network.

**Server locks** (in `server.py`):

| Lock | What it does |
|---|---|
| Timeout | 10 s per run. A one-shot container is killed. In a session, only the program stops and the session survives. |
| Output cap | Output is cut at 64 KB. |
| Rate limit | 10 `run_code` calls per minute. |
| Concurrency cap | At most 3 containers running at the same moment; extra calls wait their turn. |
| Session cap | At most 5 sessions at once. |
| Idle sweeper | A background thread kills sessions unused for 5 minutes. Leftover containers are also cleaned at startup. |
| Input checks | `session_id` must match `[0-9a-f]{8}`. File paths are checked, then resolved again inside the container so a symlink can't lead out of `/work`. |
| Job log | SQLite with parameterized queries (code and output are untrusted data). |

## Attack tests

`python run_attacks.py` fires 9 attacks at the sandbox, each in a fresh container, and reports
whether each one was blocked:

```
PASS  network is off   (exit=0, 0.9s)
PASS  memory limit (1 GB)   (exit=137, 0.9s)
PASS  too many threads   (exit=0, 3.4s)
PASS  infinite loop   (exit=None, 8.3s)
PASS  fill the disk (100 MB)   (exit=0, 0.5s)
PASS  write outside /work   (exit=0, 0.6s)
PASS  become root   (exit=0, 0.4s)
PASS  open 100 files   (exit=0, 0.4s)
PASS  docker socket / host drive   (exit=0, 0.4s)

9/9 attacks blocked
```

| Attack | How it was stopped |
|---|---|
| Open the internet | No network interface, the DNS lookup fails. |
| Allocate 1 GB | Killed by the kernel at the 256 MB limit (exit 137). |
| Start 200 threads | Refused at the 64-process limit. |
| Infinite loop | Killed by the timeout. |
| Write 100 MB | "No space left on device" at 64 MB. |
| Write to `/etc` | Read-only file system. |
| Become root | `setuid(0)` returns "Operation not permitted". |
| Open 100 files | "Too many open files" at the limit of 64. |
| Docker socket / host drive | Not present in the container. |

Other checks:

- `python test_paths.py` covers the path rules (`../x`, `/etc/passwd`, null bytes and more).
- `python test_concurrency.py` sends 6 runs at once and shows only 3 execute at the same time.

## Setup

Requirements: Python 3.12+, Docker (Docker Desktop on Windows/macOS).

```powershell
git clone <this repo>
cd sandbox-mcp
python -m venv .sandenv
.sandenv\Scripts\activate
pip install -r requirements.txt
docker pull python:3.12-slim
```

Add it to your MCP client's config, for example:

```json
{
  "mcpServers": {
    "sandbox": {
      "command": "C:/path/to/sandbox-mcp/.sandenv/Scripts/python.exe",
      "args": ["C:/path/to/sandbox-mcp/server.py"]
    }
  }
}
```

To try the tools by hand, run `mcp dev server.py` and open the Inspector.

## Project layout

```
server.py            MCP server: tools, limits, job log, idle sweeper
locks.py             the container flags (shared by the server and the attack tests)
paths.py             safe_path(): file path checks
run_attacks.py       attack tests
test_paths.py        path rule tests
test_concurrency.py  concurrency cap test
jobs.db              created at runtime (not committed)
```

## Limits (honest ones)

- **Containers share a kernel.** On Docker Desktop that is the Docker Desktop VM's kernel, not the
  host's. A microVM or gVisor would be a stronger boundary.
- **No authentication.** The server runs over stdio on your own machine. A shared or HTTP version
  would need auth first.
- **State lives in memory.** The rate limiter and the session list reset when the server restarts
  (leftover session containers are killed at startup).
- **Standard library only.** The image is plain `python:3.12-slim`. More packages mean building
  your own image, which is a deliberate choice (the sandbox can't `pip install`).
- **Output is read fully, then cut.** A program printing gigabytes would use server memory before
  the cut. Reading with an early stop is a known improvement.
- **Text files only** for `write_file` / `read_file` (UTF-8, 1 MB).

## Ideas for next

HTTP transport with auth, gVisor as the container runtime, run replay from the job log, resource
profiles (small / medium / large), a `list_sessions` tool, running several snippets in parallel.