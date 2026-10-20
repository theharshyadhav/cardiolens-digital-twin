# Convenience targets. Everything here is also documented as a plain command in README.md.
.PHONY: help install build check test test-fast serve docker clean
help:
	@echo "make install    pip + npm dependencies (full development environment)"
	@echo "make build      rebuild web/index.html and web/index.offline.html from the sources"
	@echo "make check      fail if the committed build is stale"
	@echo "make test       all 7 test suites (about 3 min; needs chromium: python3 -m playwright install chromium)"
	@echo "make test-fast  the Node suites only (about 20 s)"
	@echo "make serve      page + API at http://127.0.0.1:8000"
	@echo "make docker     build and run the container on port 8000"

install:
	pip install -r requirements.txt
	npm ci --no-audit --no-fund
	python3 -m playwright install chromium

build:
	python3 build.py

check:
	python3 build.py --check

test:
	python3 tests/run_all.py

test-fast:
	npm test

serve:
	python3 -m uvicorn backend.server:app --port 8000

docker:
	docker build -t cardiolens . && docker run --rm -p 8000:8000 cardiolens

clean:
	rm -rf results/screens results/fixtures results/_bad.nii node_modules
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
