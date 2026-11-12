import threading, time
import server

run = getattr(server.run_code, "fn", server.run_code)

def worker(i):
    t = time.time()
    out = run("import time; time.sleep(5); print('done')")
    print(f"call {i}: {time.time() - t:.1f}s -> {out.strip()}")

threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
for t in threads:
    t.start()
for t in threads:
    t.join()