.PHONY: install test test-unit test-integration test-regression clean demo experiments

install:
	pip install -e .[dev]

test:
	python -m pytest tests/ -v --tb=short

test-unit:
	python -m pytest tests/unit/ -v --tb=short

test-integration:
	python -m pytest tests/integration/ -v --tb=short

test-regression:
	python -m pytest tests/regression/ -v --tb=short

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, True) for p in pathlib.Path('.').rglob('__pycache__')]"

demo:
	python scripts/run_demo.py

experiments:
	python scripts/run_experiments.py --config configs/experiments.yaml
