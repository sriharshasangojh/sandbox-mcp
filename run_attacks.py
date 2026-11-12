import subprocess
import sys
import time
import uuid

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

def run(code, timeout=15):
    """Run code in a throwaway container with the same locks as the server."""
    name = "attack" + uuid.uuid4().hex[:8]
    cmd = ["docker", "run", "--rm", *LOCKS, "--name", name,
           "-i", "python:3.12-slim", "python", "-"]
    try:
        r = subprocess.run(cmd, input=code, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True)
        return None, "TIMEOUT"
    return r.returncode, r.stdout + r.stderr


# (name, timeout, code, check). check(exit_code, output) must return True if the attack was blocked.
ATTACKS = [
    ("network is off", 15, """
import urllib.request
try:
    urllib.request.urlopen('https://example.com', timeout=5)
    print('NETWORK OPEN')
except Exception as e:
    print('blocked:', e)
""", lambda ec, out: "blocked:" in out),

    ("memory limit (1 GB)", 15, """
x = b'a' * (1024 * 1024 * 1024)
print('NOT STOPPED')
""", lambda ec, out: ec == 137),

    ("too many threads", 15, """
import threading, time
n = 0
try:
    for _ in range(200):
        threading.Thread(target=time.sleep, args=(3,)).start()
        n += 1
    print('NOT STOPPED', n)
except Exception as e:
    print('stopped at', n, e)
""", lambda ec, out: "stopped at" in out),

    ("infinite loop", 8, """
while True:
    pass
""", lambda ec, out: out == "TIMEOUT"),

    ("fill the disk (100 MB)", 15, """
try:
    with open('/work/big', 'wb') as f:
        for _ in range(100):
            f.write(b'x' * 1024 * 1024)
            f.flush()
    print('NOT STOPPED')
except Exception as e:
    print('blocked:', e)
""", lambda ec, out: "blocked:" in out),

    ("write outside /work", 15, """
try:
    open('/etc/evil', 'w').write('hi')
    print('NOT BLOCKED')
except Exception as e:
    print('blocked:', e)
""", lambda ec, out: "blocked:" in out),

    ("become root", 15, """
import os
print('uid', os.getuid())
try:
    os.setuid(0)
    print('BECAME ROOT')
except Exception as e:
    print('blocked:', e)
""", lambda ec, out: "uid 1234" in out and "blocked:" in out),

    ("open 100 files", 15, """
fs = []
try:
    for i in range(100):
        fs.append(open('/work/f%d' % i, 'w'))
    print('NOT STOPPED')
except Exception as e:
    print('blocked at', len(fs), e)
""", lambda ec, out: "blocked at" in out),

    ("docker socket / host drive", 15, """
import os
found = os.path.exists('/var/run/docker.sock') or os.path.exists('/mnt/c')
print('FOUND' if found else 'absent')
""", lambda ec, out: "absent" in out),
]


failed = 0
for name, timeout, code, check in ATTACKS:
    started = time.time()
    ec, out = run(code, timeout)
    ok = check(ec, out)
    print(("PASS  " if ok else "FAIL  ") + name + f"   (exit={ec}, {time.time() - started:.1f}s)")
    if not ok:
        failed += 1
        print("      output:", out[:300])

print(f"\n{len(ATTACKS) - failed}/{len(ATTACKS)} attacks blocked")
sys.exit(1 if failed else 0)