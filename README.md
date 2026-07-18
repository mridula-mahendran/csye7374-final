# Tasks API: a CI/CD pipeline where every stage is a testing tool

**CSYE7374 term project. Theme 2: Test Automation and Continuous Integration.**

This project is a small but realistic FastAPI service (the "system under test")
wrapped in a CI/CD pipeline in which **each stage is a different testing tool
acting as a quality gate**. The service exists to be tested. The interesting
part is the pipeline and the tools.

The spine of the whole project is one sentence:

> Coverage tells you the line ran. Mutation testing tells you a bug on that line
> would be caught. Schemathesis tells you the API honors its own contract on
> inputs you never wrote a test for. k6 tells you it is fast enough. No single
> tool answers all four questions, so a serious pipeline runs all of them.

---

## The pipeline at a glance

```
  git push / pull request
          |
          v
  +-------------------+     Gate 1: STATIC ANALYSIS  (fast, no services)
  |  ruff  (lint)     |     ruff catches dead code and bug patterns
  |  bandit (SAST)    |     bandit flags insecure code (shift-left security)
  |  mypy  (types)    |     mypy checks types (advisory by default)
  +-------------------+
          |
          v
  +-------------------+     Gate 2: UNIT + INTEGRATION  (real Postgres)
  |  pytest           |     example-based tests: does it behave?
  |  coverage.py >=85 |     coverage gate: did the lines even run?
  +-------------------+
          |
   +------+------+
   |             |
   v             v
+-----------+  +-------------+   Gate 3 + 4 run in parallel against the live app
| SCHEMA-   |  |  k6         |
| THESIS    |  |  (load)     |   Gate 3: property-based + stateful API testing
| (contract)|  |             |   Gate 4: p95 latency and error-rate budgets
+-----------+  +-------------+
          |
          v
  on merge to main: build image, deploy, post-deploy smoke test

  ----------------------------------------------------------------
  nightly (separate schedule):  MUTMUT  mutation testing (report-only)
  "are the tests that give us 85 percent coverage actually good tests?"
```

Blocking gates fail the build on a red result. Mutation testing runs nightly and
is report-only on purpose (explained in Critical evaluation).

---

## Repository layout

```
app/
  main.py            FastAPI app, lifespan, router wiring, /health
  config.py          settings via pydantic-settings
  database.py        async SQLAlchemy engine (NullPool in test mode)
  models.py          User and Task ORM models
  schemas.py         pydantic request/response models
  security.py        Argon2 hashing + JWT (mutation target)
  deps.py            auth dependencies + admin guard
  rules.py           is_actionable business rule (mutation target)
  routers/
    auth.py          register + OAuth2 token
    users.py         GET /users/me
    tasks.py         CRUD, list, stats, OpenAPI links, ownership check
    admin.py         admin-only listing (RBAC)
tests/
  conftest.py        async fixtures (client, auth_client, admin_client)
  test_auth.py       registration + login
  test_tasks.py      CRUD, pagination, filtering, validation
  test_authorization.py  IDOR tests (the example-based gate)
  test_admin.py      RBAC
  test_stats.py      pins the is_actionable boundary (mutation target)
perf/
  smoke.js           k6 load test with thresholds
.github/workflows/
  ci.yml             static, unit+coverage, contract, performance
  mutation.yml       nightly mutmut (report-only)
Dockerfile, docker-compose.yml, db/init.sql, Makefile, pyproject.toml
```

---

## The system under test

A task-management API with realistic backend concerns, so the tools have
something meaningful to bite on:

* OAuth2 password flow, JWT bearer tokens, Argon2 password hashing.
* Role-based access control (a normal `user` role and an `admin` role).
* Full CRUD on a `Task` resource with pagination and status filtering.
* Per-user ownership: you can only see and change your own tasks.
* OpenAPI `links` declared on create so Schemathesis can chain
  create then get then update then delete during stateful testing.

Endpoints: `POST /auth/register`, `POST /auth/token`, `GET /users/me`,
`POST /tasks`, `GET /tasks`, `GET /tasks/stats`, `GET /tasks/{id}`,
`PATCH /tasks/{id}`, `DELETE /tasks/{id}`, `GET /admin/tasks`, `GET /health`.

---

## The tools

| Tool | Pipeline layer | Question it answers | What makes it distinctive | Gate |
| --- | --- | --- | --- | --- |
| **pytest + coverage.py** | unit / integration | Does the code behave, and did the tests run it? | The baseline every other tool is measured against | coverage `--fail-under=85` |
| **Schemathesis** | contract / property-based | Does the API honor its OpenAPI contract on generated inputs, including multi-step workflows? | Tests are derived from the schema with near-zero maintenance; finds edge cases humans miss | non-zero exit on any failing check |
| **k6** | performance | Is it fast enough under load? | Native thresholds turn a load test into a pass/fail gate | threshold breach exits non-zero |
| **mutmut** | test-quality (meta) | Are the passing tests actually good, or just present? | Measures the tests, not the code, by injecting bugs and checking the suite catches them | report-only, nightly |
| **Bandit** | static security | Is there insecure code (shift-left)? | Fast AST-based security scan, no running app needed | blocking |

---

## Quickstart

Requires Docker and Python 3.12.

```bash
# 1. dependencies
make dev-install

# 2. start Postgres (also creates appdb and appdb_test)
make db-up

# 3. run the tests behind the coverage gate
make cov

# 4. run the API and open the docs
make run
#    then visit http://localhost:8000/docs
```

Run any individual gate:

```bash
make lint          # ruff
make sast          # bandit
make type          # mypy
make cov           # pytest + coverage gate

# Schemathesis and k6 need the API running. In one terminal: make run
# In another, mint a token and point the tools at the live app:
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -d "username=demo@example.com&password=Str0ngPassw0rd!" \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
make schemathesis TOKEN=$TOKEN
make k6

make mutmut        # mutation testing
make mutmut-report # results + HTML report in ./html
```

(Register `demo@example.com` first, or use any account you create.)

---

## The demo playbook

This is the heart of the presentation. Each bug below is a one line or two line
change that turns exactly one gate red while the others stay green. Together they
show what each tool uniquely catches and, just as important, what it is blind to.

Keep `main` green. For each demo, apply the change, run the gate, show it go red,
then revert with `git checkout .`.

### Bug 1: Schemathesis catches a crash that the unit tests miss

**Change** in `app/routers/tasks.py`, inside `create_task`, add one line after
building the task:

```python
    task = Task(owner_id=user.id, **payload.model_dump())
    _ = payload.title.encode("ascii")   # BUG: crashes on any non-ASCII title
    db.add(task)
```

**Run:** `make schemathesis TOKEN=$TOKEN`

**Result:** the hand-written tests all use ASCII titles, so `make cov` stays
green. Schemathesis generates unicode strings, hits the `UnicodeEncodeError`,
gets a 500, and the `not_a_server_error` check fails with a reproducible example
(a minimal failing title) and a curl command to replay it.

**Point:** property-based testing explores the input space that example-based
tests, by definition, do not. You did not have to imagine the bad input.

### Bug 2: the example-based tests catch an IDOR that Schemathesis cannot

**Change** in `app/routers/tasks.py`, inside `_get_owned_task`, comment out the
authorization check:

```python
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    # if task.owner_id != user.id and user.role != Role.admin:   # BUG: IDOR
    #     raise HTTPException(status_code=404, detail="Task not found")
    return task
```

**Run:** `make cov`

**Result:** `tests/test_authorization.py` fails: user B can now read and modify
user A's task. Schemathesis, if you run it, stays green, because it drives the
API as a single identity and every response is schema-valid. A cross-user data
leak looks exactly like a normal, correct 200.

**Point:** this is the ceiling of schema-derived testing. It validates shape and
status, not business meaning or authorization. You still need example-based
tests that encode intent.

### Bug 3: mutation testing reveals a weak test that coverage rates 100 percent

**Change** in `tests/test_stats.py`, weaken the assertion:

```python
    assert body["total"] == 3
    assert body["actionable"] >= 0     # BUG: was == 1, now asserts nothing useful
```

**Run:**

```bash
make cov          # still green, and rules.py still shows 100 percent coverage
make mutmut
make mutmut-report
```

**Result:** coverage is unchanged, because the weakened test still executes
every line of `rules.py`. But `mutmut` now reports a **surviving mutant**: it
changed `priority >= 3` to `priority > 3` in `is_actionable`, and no test failed.
The lazy assertion never checks the boundary, so the mutant slips through.

**Point:** coverage answers "did the line run". Mutation testing answers "would
a bug on that line be caught". They are different questions, and this is the
cleanest way to show it live.

### Bug 4: k6 catches a latency regression that no functional test notices

**Change** in `app/routers/tasks.py`, add an import at the top and a sleep inside
`list_tasks`:

```python
import asyncio   # at the top of the file

# ... inside list_tasks, before building the query:
    await asyncio.sleep(0.4)   # BUG: 400ms latency regression
```

**Run:** with the API running, `make k6`

**Result:** every response is still a correct 200, so `make cov` and Schemathesis
stay green. k6 sees p95 latency blow past the 500ms budget, the
`http_req_duration` threshold is breached, k6 exits non-zero, and the gate fails.

**Point:** correctness and performance are orthogonal. A functional suite will
happily pass a service that has become unusably slow. Performance needs its own
gate with an explicit budget.

### The demo in one table

| Bug | Green gates (miss it) | Red gate (catches it) | Lesson |
| --- | --- | --- | --- |
| Non-ASCII crash | pytest/coverage | Schemathesis | property-based finds unimagined inputs |
| IDOR | Schemathesis | pytest authorization | schema testing cannot see authorization |
| Weak assertion | coverage (still 100%) | mutmut | coverage is not test quality |
| Latency | pytest, Schemathesis | k6 | correctness is not performance |

---

## What the CI pipeline does

`.github/workflows/ci.yml` runs on every push and pull request:

* **static**: installs deps, runs `ruff check`, `bandit -ll -r app`, and `mypy`
  (advisory). No database, so it is fast and gives quick feedback.
* **unit**: spins up a Postgres service container, runs the suite under
  `coverage`, and fails if coverage drops below 85 percent. Uploads the coverage
  XML as an artifact.
* **contract**: starts the app in the background, waits for `/health`, registers
  a user and mints a JWT with curl, then runs Schemathesis against the live
  OpenAPI schema with that token. Stateful testing is enabled by default, so
  Schemathesis chains create then get then update then delete using the OpenAPI
  links declared on `POST /tasks`.
* **performance**: starts the app and runs the k6 smoke test through the official
  `grafana/k6` container with host networking. The thresholds in `perf/smoke.js`
  are the pass/fail condition.

`.github/workflows/mutation.yml` runs nightly (and on demand). It runs `mutmut`
on the high-value modules, prints results, and uploads an HTML report as an
artifact. It does not fail the build (see below).

---

## Critical evaluation

Rubric point four asks for honest assessment, not a sales pitch. Every tool here
earns its place, and every tool has real limits.

**pytest + coverage.py.** The dependable foundation, and the thing all the other
tools are contextualized against. Its blind spot is the entire reason the other
tools exist: high coverage says lines executed, not that assertions are
meaningful (Bug 3), and example-based tests only cover inputs someone thought of
(Bug 1). Coverage is necessary and radically insufficient on its own.

**Schemathesis.** Enormous leverage: hundreds of generated cases and stateful
workflows from a schema you already maintain, with almost no per-endpoint test
code. It reliably surfaces 500s, schema drift, and validation bypasses. Limits:
it is only as good as the schema (a permissive or inaccurate spec means shallow
tests), and it fundamentally cannot judge business semantics or authorization
(Bug 2). It complements example-based tests; it does not replace them. Runtime
and flakiness also grow with `--max-examples`, so it needs tuning.

**k6.** Turns performance into a first-class, gated signal via native
thresholds, and the JavaScript scripting is approachable. Limits: CI runners are
noisy and not representative of production hardware, so absolute numbers drift
and thresholds must be set with headroom to avoid false failures. A short smoke
test catches gross regressions (Bug 4) but is not a substitute for a real,
sustained load or soak test in a production-like environment.

**mutmut.** The only tool here that measures the tests rather than the code, and
the most direct answer to "is our coverage real". Limits, and the reason it is
report-only and nightly: it is slow, because it reruns the suite once per mutant;
it produces equivalent mutants (semantically identical changes that can never be
killed) that require human judgment; and a naive "score must be 95 percent" gate
becomes theater that people game or disable. The recommended policy, which this
project follows, is a staged approach: run coverage on every pull request, run
mutation testing nightly on protected modules, and enforce "no new survivors" or
"do not drop below the reviewed baseline" rather than an absolute number.

**Bandit.** Cheap, fast, catches common insecure patterns early. Limits: it is a
pattern matcher, so it has false positives (tuned here with `-ll` for medium and
high severity) and it cannot find logic-level security flaws like the IDOR in
Bug 2. It is one layer of shift-left security, not the whole story.

The meta-point for the talk: these tools are not competitors. They are layers
that catch different, mostly non-overlapping classes of defect. The pipeline is
the argument.

---

## 2026 testing trends this project reflects

* **Contract and API-first testing.** Generating tests from an OpenAPI schema
  (Schemathesis) instead of hand-writing every case is now mainstream for
  services. It scales with the API and shrinks maintenance.
* **Property-based and generative testing.** Moving from "here are examples I
  thought of" to "explore the input space and find counterexamples" is where a
  lot of high-value bug discovery now happens.
* **Performance budgets as gates.** Treating p95 latency and error rate as
  pass/fail thresholds in CI, not as a dashboard someone checks later.
* **Shift-left security.** SAST in the pipeline (Bandit here), alongside
  dependency and secret scanning, so security feedback arrives at commit time.
* **Test-quality signals beyond coverage.** Growing adoption of mutation testing
  to answer whether a suite is actually strong, with staged, baseline-based
  policies rather than naive thresholds.
* **From test automation to test orchestration.** The unit of value is no longer
  a single automated test type but a pipeline that composes many, each answering
  a distinct question. This project is a concrete instance of that shift.
* **AI-assisted testing.** Test generation, self-healing selectors, and
  triage assistance are emerging across the ecosystem (both Schemathesis and k6
  ship AI-assist features), layered on top of the deterministic gates rather than
  replacing them.

---

## Suggested 12-minute presentation flow

* **0:00 to 1:30. The problem and the thesis.** Four questions no single tool
  answers. State the spine sentence.
* **1:30 to 3:00. The landscape.** The 2026 trends above, positioning where each
  tool sits. Covers the "comprehensive coverage" rubric point.
* **3:00 to 4:30. The system under test and the pipeline.** Show the diagram and
  the OpenAPI docs page. Explain gates vs nightly.
* **4:30 to 9:30. The four tools, in depth, by live demo.** Run the four bug
  injections. Each one is a tool going red while others stay green. This carries
  the "in-depth on 3 to 5 tools" and "practical complex scenarios" rubric points.
* **9:30 to 11:00. Critical evaluation.** Walk the strengths-and-limits section.
  Land the point that these are layers, not competitors.
* **11:00 to 12:00. Takeaways.** The pipeline is the argument. Coverage, caught,
  contract, fast enough.
* **Q&A, 3 minutes.** Likely questions: how do you keep Schemathesis fast, why
  is mutation nightly and not a gate, how do you set k6 thresholds on noisy
  runners, what would you add next (contract tests against real consumers, DAST,
  soak tests).

---

## Notes

* This repository was authored for a course demo. The code is written to be run
  and read; run the pipeline in your own environment to see the gates in action.
* Tables are created on startup for simplicity. Use Alembic migrations for a real
  deployment.
* Tool CLIs evolve. If a flag has changed in your installed version, check
  `schemathesis run --help` or `mutmut --help`; the pipeline logic does not
  depend on any exotic flags.
```
