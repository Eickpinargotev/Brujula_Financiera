# Brújula — atajos. TODO corre en Docker (nunca en el host).
.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help up down build logs sh test lint fmt typecheck restart ps

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Levanta el contenedor (build + reload)
	$(COMPOSE) up --build

down: ## Detiene y elimina el contenedor
	$(COMPOSE) down

build: ## Construye la imagen
	$(COMPOSE) build

logs: ## Sigue los logs
	$(COMPOSE) logs -f brujula

sh: ## Abre una shell dentro del contenedor
	$(COMPOSE) exec brujula bash

restart: ## Reinicia el servicio
	$(COMPOSE) restart brujula

ps: ## Estado del contenedor
	$(COMPOSE) ps

test: ## Corre los tests dentro del contenedor
	$(COMPOSE) run --rm brujula pytest

lint: ## Linter (ruff) dentro del contenedor
	$(COMPOSE) run --rm brujula ruff check .

fmt: ## Formatea (ruff) dentro del contenedor
	$(COMPOSE) run --rm brujula ruff format .

typecheck: ## Chequeo de tipos (mypy) dentro del contenedor
	$(COMPOSE) run --rm brujula mypy src
