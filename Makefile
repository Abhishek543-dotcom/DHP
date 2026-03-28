.PHONY: help dev up down logs build test clean

PYTHON ?= python3

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# =============================================
# Development
# =============================================

dev: up ## Start full development environment
	@echo "Lakehouse Platform is running!"
	@echo "  Job Service:      http://localhost:8001/docs"
	@echo "  Metadata Service: http://localhost:8002/docs"
	@echo "  Log Service:      http://localhost:8003/docs"
	@echo "  Storage Service:  http://localhost:8004/docs"
	@echo "  MinIO Console:    http://localhost:9001"
	@echo "  Grafana:          http://localhost:3000"

up: ## Start all services with docker-compose
	cd infra && docker-compose -f docker-compose.dev.yaml up -d

down: ## Stop all services
	cd infra && docker-compose -f docker-compose.dev.yaml down

logs: ## Tail logs for all services
	cd infra && docker-compose -f docker-compose.dev.yaml logs -f

restart: down up ## Restart all services

# =============================================
# Build
# =============================================

build: ## Build all Docker images
	cd infra && docker-compose -f docker-compose.dev.yaml build

build-spark: ## Build Spark base image
	docker build -t lakehouse-spark:3.5.0 spark-images/base/

# =============================================
# Individual Services (for development)
# =============================================

run-job-service: ## Run Job Service locally (requires infra running)
	cd services/job-service && uvicorn app.main:app --reload --port 8001

run-metadata-service: ## Run Metadata Service locally
	cd services/metadata-service && uvicorn app.main:app --reload --port 8002

run-log-service: ## Run Log Service locally
	cd services/log-service && uvicorn app.main:app --reload --port 8003

run-storage-service: ## Run Storage Service locally
	cd services/storage-service && uvicorn app.main:app --reload --port 8004

# =============================================
# Testing
# =============================================

test: ## Run all tests
	cd services/job-service && $(PYTHON) -m pytest tests/ -v
	cd services/metadata-service && $(PYTHON) -m pytest tests/ -v

test-job-service: ## Run Job Service tests
	cd services/job-service && $(PYTHON) -m pytest tests/ -v

test-metadata-service: ## Run Metadata Service tests
	cd services/metadata-service && $(PYTHON) -m pytest tests/ -v

# =============================================
# Database
# =============================================

db-init: ## Initialize database schema
	docker exec -i lakehouse-postgres psql -U lakehouse -d lakehouse < scripts/init-db.sql

db-reset: ## Reset database (drop and recreate)
	docker exec lakehouse-postgres psql -U lakehouse -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	docker exec -i lakehouse-postgres psql -U lakehouse -d lakehouse < scripts/init-db.sql

# =============================================
# Kubernetes
# =============================================

k8s-deploy: ## Deploy to Kubernetes
	kubectl apply -f infra/k8s/namespaces.yaml
	kubectl apply -f infra/k8s/config.yaml
	kubectl apply -f infra/k8s/fluent-bit-config.yaml
	kubectl apply -f infra/k8s/network-policy.yaml
	kubectl apply -f infra/k8s/orchestrator-deployment.yaml
	kubectl apply -f infra/k8s/job-service-deployment.yaml
	kubectl apply -f infra/k8s/metadata-service-deployment.yaml
	kubectl apply -f infra/k8s/log-service-deployment.yaml
	kubectl apply -f infra/k8s/storage-service-deployment.yaml

k8s-delete: ## Remove from Kubernetes
	kubectl delete -f infra/k8s/ --ignore-not-found

# =============================================
# Cleanup
# =============================================

clean: down ## Clean up everything
	cd infra && docker-compose -f docker-compose.dev.yaml down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

