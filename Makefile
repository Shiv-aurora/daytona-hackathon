PYTHON ?= python3

.PHONY: smoke demo
smoke:
	$(PYTHON) -m pytest -q calls/tests/test_safety.py runtime/tests/test_runtime.py eval/tests/test_scenario1_smoke.py

demo:
	$(PYTHON) -m runtime.demo --store local --score
