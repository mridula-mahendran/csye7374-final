# Uses ">" as the recipe prefix instead of a tab, which avoids whitespace issues.
.RECIPEPREFIX = >
.PHONY: help install dev-install db-up db-down run lint type sast test cov \
        schemathesis k6 mutmut mutmut-report all-checks

TEST_DB_URL = postgresql+asyncpg://postgres:postgres@localhost:5432/appdb_test

help:
> @echo "Targets:"
> @echo "  dev-install    install runtime + dev dependencies"
> @echo "  db-up / db-down   start / stop local Postgres (docker compose)"
> @echo "  run            run the API with autoreload on :8000"
> @echo "  lint           ruff lint"
> @echo "  type           mypy type check"
> @echo "  sast           bandit security scan"
> @echo "  test           run the pytest suite"
> @echo "  cov            run tests with the coverage gate (fail-under 85)"
> @echo "  schemathesis   property-based API tests (needs the API running; pass TOKEN=...)"
> @echo "  k6             smoke load test (needs the API running)"
> @echo "  mutmut         run mutation testing"
> @echo "  mutmut-report  show results and build the HTML report"
> @echo "  all-checks     lint + type + sast + cov"

install:
> pip install -r requirements.txt

dev-install:
> pip install -r requirements.txt -r requirements-dev.txt

db-up:
> docker compose up -d db

db-down:
> docker compose down

run:
> uvicorn app.main:app --reload --port 8000

lint:
> ruff check .

type:
> mypy app

sast:
> bandit -q -ll -r app

test:
> TESTING=1 DATABASE_URL=$(TEST_DB_URL) pytest -q

cov:
> TESTING=1 DATABASE_URL=$(TEST_DB_URL) coverage run -m pytest -q
> coverage report --fail-under=85

schemathesis:
> schemathesis run http://localhost:8000/openapi.json --max-examples=150 --exclude-checks positive_data_acceptance,unsupported_method --header "Authorization: Bearer $(TOKEN)"

k6:
> docker run --rm --network host -e BASE_URL=http://localhost:8000 -e VUS=10 -e DURATION=20s -v "$(PWD)/perf:/perf" grafana/k6 run /perf/smoke.js

mutmut:
> TESTING=1 DATABASE_URL=$(TEST_DB_URL) mutmut run

mutmut-report:
> mutmut results
> mutmut html

all-checks: lint type sast cov
