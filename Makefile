.PHONY: test lint run

test:
	python -m pytest

lint:
	ruff check .
	ruff format --check .
	mypy natter

run:
	python -m natter
