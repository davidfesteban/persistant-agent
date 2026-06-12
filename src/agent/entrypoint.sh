#!/bin/sh
set -eu

codex app-server \
  --listen ws://127.0.0.1:8081 \
  -c sandbox_mode=\"danger-full-access\" \
  -c approval_policy=\"never\" &

exec socat TCP-LISTEN:8080,fork,reuseaddr TCP:127.0.0.1:8081
