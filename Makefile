SHELL := /bin/sh

.DEFAULT_GOAL := help
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then printf '.venv/bin/python'; elif command -v python3.12 >/dev/null 2>&1; then command -v python3.12; else command -v python3; fi)
MACHINE_HOST ?= 127.0.0.1
MACHINE_PORT ?= 8765
MACHINE_URL ?= http://$(MACHINE_HOST):$(MACHINE_PORT)

ACTION := $(word 1,$(MAKECMDGOALS))
ARG1 := $(word 2,$(MAKECMDGOALS))
ARG2 := $(word 3,$(MAKECMDGOALS))
EXTRA_GOALS := $(filter-out help machine start stop agents,$(MAKECMDGOALS))

CODE_PATH ?= $(ARG1)
AGENT_NAME ?= $(if $(filter start,$(ACTION)),$(ARG2),$(ARG1))

.PHONY: help machine start stop agents $(EXTRA_GOALS)

help:
	@printf '%s\n' \
		'Usage:' \
		'  make machine' \
		'  make start /absolute/path/to/repo agent-name' \
		'  make stop agent-name' \
		'  make agents'

machine:
	@PYTHONPATH=src "$(PYTHON)" -m uvicorn machine.app:app --host "$(MACHINE_HOST)" --port "$(MACHINE_PORT)"

start:
	@test -n "$(CODE_PATH)" || { echo "Missing code path. Usage: make start /absolute/path/to/repo agent-name"; exit 2; }
	@test -n "$(AGENT_NAME)" || { echo "Missing agent name. Usage: make start /absolute/path/to/repo agent-name"; exit 2; }
	@test -d "$(CODE_PATH)" || { echo "Code path does not exist: $(CODE_PATH)"; exit 2; }
	@payload=$$("$(PYTHON)" -c 'import json,sys; print(json.dumps({"repo_path": sys.argv[1]}))' "$(CODE_PATH)"); \
	curl -fsS -X POST "$(MACHINE_URL)/agents/$(AGENT_NAME)/start" -H 'content-type: application/json' -d "$$payload"; \
	printf '\n'

stop:
	@test -n "$(AGENT_NAME)" || { echo "Missing agent name. Usage: make stop agent-name"; exit 2; }
	@curl -fsS -X POST "$(MACHINE_URL)/agents/$(AGENT_NAME)/stop"; printf '\n'

agents:
	@curl -fsS "$(MACHINE_URL)/agents"; printf '\n'

$(EXTRA_GOALS):
	@:

%:
	@:
