SHELL := /bin/sh

.DEFAULT_GOAL := help
PYTHON ?= $(shell if [ -x .venv/bin/python ]; then printf '.venv/bin/python'; elif command -v python3.12 >/dev/null 2>&1; then command -v python3.12; else command -v python3; fi)
MACHINE_HOST ?= 127.0.0.1
MACHINE_PORT ?= 8765
MACHINE_URL ?= http://$(MACHINE_HOST):$(MACHINE_PORT)

ACTION := $(word 1,$(MAKECMDGOALS))
ARG1 := $(word 2,$(MAKECMDGOALS))
ARG2 := $(word 3,$(MAKECMDGOALS))
EXTRA_GOALS := $(filter-out help start stop machine-start machine-stop agents,$(MAKECMDGOALS))

CODE_PATH ?= $(ARG1)
AGENT_NAME ?= $(if $(filter start,$(ACTION)),$(ARG2),$(ARG1))
COMPOSE_PROJECT := persistant-agent-$(AGENT_NAME)

.PHONY: help start stop machine-start machine-stop agents $(EXTRA_GOALS)

help:
	@printf '%s\n' \
		'Usage:' \
		'  make machine-start' \
		'  make machine-stop' \
		'  make start /absolute/path/to/repo agent-name' \
		'  make stop agent-name' \
		'  make agents'

machine-start:
	@PYTHONPATH=src PERSISTANT_MACHINE_HOST="$(MACHINE_HOST)" PERSISTANT_MACHINE_PORT="$(MACHINE_PORT)" PERSISTANT_MACHINE_URL="$(MACHINE_URL)" "$(PYTHON)" -m persistant_agent.machine_daemon start

machine-stop:
	@PYTHONPATH=src PERSISTANT_MACHINE_URL="$(MACHINE_URL)" "$(PYTHON)" -m persistant_agent.machine_daemon stop

start:
	@test -n "$(CODE_PATH)" || { echo "Missing code path. Usage: make start /absolute/path/to/repo agent-name"; exit 2; }
	@test -n "$(AGENT_NAME)" || { echo "Missing agent name. Usage: make start /absolute/path/to/repo agent-name"; exit 2; }
	@test -d "$(CODE_PATH)" || { echo "Code path does not exist: $(CODE_PATH)"; exit 2; }
	@$(MAKE) --no-print-directory machine-start
	@PYTHONPATH=src PERSISTANT_MACHINE_URL="$(MACHINE_URL)" "$(PYTHON)" -m persistant_agent.machine_cli start "$(CODE_PATH)" "$(AGENT_NAME)"

stop:
	@test -n "$(AGENT_NAME)" || { echo "Missing agent name. Usage: make stop agent-name"; exit 2; }
	@$(MAKE) --no-print-directory machine-start
	@PYTHONPATH=src PERSISTANT_MACHINE_URL="$(MACHINE_URL)" "$(PYTHON)" -m persistant_agent.machine_cli stop "$(AGENT_NAME)"

agents:
	@$(MAKE) --no-print-directory machine-start
	@PYTHONPATH=src PERSISTANT_MACHINE_URL="$(MACHINE_URL)" "$(PYTHON)" -m persistant_agent.machine_cli agents

$(EXTRA_GOALS):
	@:

%:
	@:
