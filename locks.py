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