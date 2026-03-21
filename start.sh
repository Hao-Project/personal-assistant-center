#!/bin/bash
cd "$(dirname "$0")"
echo "Starting Personal Assistant Center..."
python3 server.py &
SERVER_PID=$!
sleep 1
open http://127.0.0.1:5000
wait $SERVER_PID
