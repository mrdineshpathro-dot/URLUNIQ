PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

.PHONY: help install dev-install uninstall test lint format typecheck check bench example clean build

help:
	@echo "URLUNIQ 2.0 development targets:"
	@echo "  make dev-install   - install package in editable mode with dev tools"
	@echo "  make install       - install the package"
	@echo "  make test          - run the full test suite"
	@echo "  make lint          - run ruff checks"
	@echo "  make format        - format code with black + ruff"
	@echo "  make typecheck     - run mypy"
	@echo "  make check         - lint + typecheck + test"
	@echo "  make bench         - run the benchmark suite (quick sizes)"
	@echo "  make example       - run URLUNIQ on examples/urls.txt"
	@echo "  make build         - build sdist + wheel"
	@echo "  make clean         - remove caches and build artifacts"

install:
	$(PIP) install .

dev-install:
	$(PIP) install -e ".[dev]"

uninstall:
	$(PIP) uninstall -y urluniq

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests benchmarks

format:
	$(PYTHON) -m black src tests benchmarks
	$(PYTHON) -m ruff check --fix src tests benchmarks

typecheck:
	$(PYTHON) -m mypy

check: lint typecheck test

bench:
	$(PYTHON) benchmarks/run_benchmark.py --quick

example:
	$(PYTHON) -m urluniq clean -i examples/urls.txt -o /tmp/urluniq_clean.txt --stats

build:
	$(PYTHON) -m build

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
