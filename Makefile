.PHONY: install run lint

install:
	uv sync --locked

run:
	uv run database

lint:
	uv run ruff check .
