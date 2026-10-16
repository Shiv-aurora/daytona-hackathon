PYTHON ?= python3

.PHONY: check-surreal check-daytona check-elevenlabs smoke demo demo-surreal demo-legacy serve
check-surreal:
	$(PYTHON) scripts/check_surreal.py

smoke:
	$(PYTHON) -m pytest -q calls/tests/test_safety.py runtime/tests/test_runtime.py eval/tests/test_scenario1_smoke.py tests/test_recovery_integration.py

demo:
	$(PYTHON) -m api.demo --store memory

demo-surreal:
	SURREAL_URL=mem:// $(PYTHON) -m api.demo --store surreal

serve:
	$(PYTHON) -m api.server --store surreal --port 8787

demo-legacy:
	$(PYTHON) -m runtime.demo --store local --score

check-daytona:
	$(PYTHON) scripts/check_daytona.py

check-elevenlabs:
	$(PYTHON) scripts/check_elevenlabs.py $(if $(STT),--stt $(STT),)
