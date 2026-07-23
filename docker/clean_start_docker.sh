#!/bin/bash
# Docker Desktop clean start for this machine (Windows).
#
# Every Docker session on this host leaves undeletable zombie AF_UNIX socket
# files (dockerInference, engine.sock, ...) under AppData; the next start then
# dies with "The file cannot be accessed by the system". Deleting the files is
# impossible (broken reparse entries) but renaming the parent dir works —
# Docker recreates it fresh. Run this INSTEAD of starting Docker Desktop
# directly. Safe to run repeatedly.
set -u
TS=$(date +%s)
# Windows per-user AppData\Local as a Git Bash path (e.g. /c/Users/<user>/AppData/Local)
LOCAL="$(cygpath -u "${LOCALAPPDATA:?LOCALAPPDATA not set — run from Git Bash on Windows}")"

# 1) fully stop anything running (graceful first, then hard)
export PATH="/c/Program Files/Docker/Docker/resources/bin:$PATH"
docker desktop stop >/dev/null 2>&1
powershell -NoProfile -Command "'Docker Desktop','com.docker.backend','com.docker.build','docker-desktop','docker' | ForEach-Object { Stop-Process -Name \$_ -Force -ErrorAction SilentlyContinue }" >/dev/null 2>&1
sleep 3
powershell -NoProfile -Command "wsl --shutdown" >/dev/null 2>&1
sleep 2

# 2) quarantine zombie-socket dirs (rename, never delete)
for d in "$LOCAL/Docker/run" "$LOCAL/docker-secrets-engine"; do
    if [ -d "$d" ]; then
        mv "$d" "${d}_stale_${TS}" 2>/dev/null && echo "quarantined: $d"
    fi
done

# 3) start and wait for the engine
powershell -NoProfile -Command "Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'" >/dev/null 2>&1
for i in $(seq 1 40); do
    v=$(timeout 8 docker info --format '{{.ServerVersion}}' 2>/dev/null)
    if [ -n "$v" ]; then
        echo "ENGINE UP: $v (after ~$((i*7))s)"
        exit 0
    fi
    sleep 5
done
echo "ENGINE FAILED TO START; last backend error:"
grep -aiE "reporting error to user" "$(ls -t $LOCAL/Docker/log/host/com.docker.backend*.log | head -1)" | tail -1
exit 1
