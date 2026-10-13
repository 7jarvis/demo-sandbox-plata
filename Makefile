SHELL := /bin/bash
export BASE_URL ?= http://localhost:8000
export SANDBOX_OTP_CODE ?= 111111
PYTEST := python -m pytest --alluredir=allure-results

.PHONY: help up down logs install test smoke regression api ui lint fmt report clean

help: ## Show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-11s %s\n", $$1, $$2}'

up: ## Build and start the app, wait until healthy
	docker compose up -d --build --wait

down: ## Stop the app and drop its data
	docker compose down -v

logs: ## Follow app logs
	docker compose logs -f cardpay

install: ## Install test dependencies and Chromium
	pip install -r requirements-tests.txt
	python -m playwright install --with-deps chromium

smoke: ## Smoke suite (critical path, API + UI)
	$(PYTEST) -m smoke

regression: ## Full suite
	$(PYTEST) -m regression

test: regression ## Same as regression

api: ## API tests only
	$(PYTEST) -m api

ui: ## UI tests only (HEADED=1 to watch the browser)
	$(PYTEST) -m ui $(if $(filter 1,$(HEADED)),--headed --slowmo 300,)

lint: ## ruff + mypy
	ruff check .
	ruff format --check .
	mypy

fmt: ## Format code
	ruff format .
	ruff check --fix .

report: ## Open the Allure report of the last local run
	allure serve allure-results

clean: ## Remove local test output
	rm -rf allure-results allure-report test-results .pytest_cache
