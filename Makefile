PYTHON ?= python3

.PHONY: all verify qa test refresh clean

all:
	$(PYTHON) src/run_pipeline.py

verify:
	$(PYTHON) src/verify_exports.py --repo .

qa:
	$(PYTHON) src/qa_checks.py --repo .
	$(PYTHON) src/verify_exports.py --repo .

test:
	$(PYTHON) -m unittest discover -s tests -v

refresh:
	$(PYTHON) src/run_pipeline.py --refresh-rxnorm --allow-rxnorm-version-change

clean:
	$(PYTHON) src/clean_work.py --repo .
