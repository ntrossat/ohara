.PHONY: dev init

# Run Ohara with Docker Compose, rebuilding on code changes. Reads OHARA_URL from .env.
dev:
	docker compose up --build --watch

# Start over from a fresh install: removes the container, the image, and the data volume (settings, sessions, docs).
init:
	docker compose down --volumes --rmi local --remove-orphans
	@echo "Data removed. Setup creates a new GitHub App: delete the old one in GitHub > Settings > Developer settings > GitHub Apps."
	$(MAKE) dev
