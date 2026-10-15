.PHONY: generate lint typecheck test verify run

PYTHON ?= .venv/bin/python

generate:
	$(PYTHON) tools/generate_protos.py

lint:
	$(PYTHON) -m ruff check app tests tools

typecheck:
	$(PYTHON) -m mypy app tests tools

test:
	$(PYTHON) -m pytest -q

verify: lint typecheck test

run:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000
