.PHONY: install run lint test

install:
	uv sync --locked

run:
	uv run database

lint:
	uv run ruff check .

test:
	uv run python -m unittest discover -s tests -v
