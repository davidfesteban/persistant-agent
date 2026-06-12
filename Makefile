SHELL := /bin/sh

.DEFAULT_GOAL := help

ACTION := $(word 1,$(MAKECMDGOALS))
ARG1 := $(word 2,$(MAKECMDGOALS))
ARG2 := $(word 3,$(MAKECMDGOALS))
EXTRA_GOALS := $(filter-out help start stop,$(MAKECMDGOALS))

CODE_PATH ?= $(ARG1)
AGENT_NAME ?= $(if $(filter start,$(ACTION)),$(ARG2),$(ARG1))
COMPOSE_PROJECT := persistant-agent-$(AGENT_NAME)

.PHONY: help start stop $(EXTRA_GOALS)

help:
	@printf '%s\n' \
		'Usage:' \
		'  make start /absolute/path/to/repo agent-name' \
		'  make stop agent-name'

start:
	@test -n "$(CODE_PATH)" || { echo "Missing code path. Usage: make start /absolute/path/to/repo agent-name"; exit 2; }
	@test -n "$(AGENT_NAME)" || { echo "Missing agent name. Usage: make start /absolute/path/to/repo agent-name"; exit 2; }
	@test -d "$(CODE_PATH)" || { echo "Code path does not exist: $(CODE_PATH)"; exit 2; }
	@REPOSITORY_PATH="$(CODE_PATH)" AGENT_NAME="$(AGENT_NAME)" docker compose -p "$(COMPOSE_PROJECT)" up -d --build
	@PORT="$$(REPOSITORY_PATH="$(CODE_PATH)" AGENT_NAME="$(AGENT_NAME)" docker compose -p "$(COMPOSE_PROJECT)" port agent 8080 | sed 's/.*://')"; \
		i=0; \
		while [ "$$i" -lt 30 ]; do \
			curl -fsS "http://127.0.0.1:$$PORT/health" >/dev/null 2>&1 && break; \
			i=$$((i + 1)); \
			sleep 1; \
		done; \
		if [ "$$i" -eq 30 ]; then \
			REPOSITORY_PATH="$(CODE_PATH)" AGENT_NAME="$(AGENT_NAME)" docker compose -p "$(COMPOSE_PROJECT)" logs --tail 80 agent; \
			echo "Agent $(AGENT_NAME) did not become healthy"; \
			exit 1; \
		fi
	@printf 'Agent %s started for %s\n' "$(AGENT_NAME)" "$(CODE_PATH)"
	@printf 'API: http://localhost:%s\n' "$$(REPOSITORY_PATH="$(CODE_PATH)" AGENT_NAME="$(AGENT_NAME)" docker compose -p "$(COMPOSE_PROJECT)" port agent 8080 | sed 's/.*://')"

stop:
	@test -n "$(AGENT_NAME)" || { echo "Missing agent name. Usage: make stop agent-name"; exit 2; }
	@REPOSITORY_PATH="$(PWD)" AGENT_NAME="$(AGENT_NAME)" docker compose -p "$(COMPOSE_PROJECT)" down
	@printf 'Agent %s stopped\n' "$(AGENT_NAME)"

$(EXTRA_GOALS):
	@:

%:
	@:
