# LabLens

**Check the reasoning behind your school lab graph.**

LabLens preserves two-column measurements, converts units, fits a declared model, and explains deterministic checks about dimensions, transformations, and assumptions. Its numerical results work without any AI API key.

**Start here: [Running.md](RUNNING.md).** The release evidence and remaining public-launch gates are in [docs/RELEASE_STATUS.md](docs/RELEASE_STATUS.md). A built application is not a claim of completed hosted deployment, human accessibility review, or hackathon submission.

## What works

- Anonymous, private browser workspaces; no names, emails, school rosters, or grades requested.
- Manual entry or UTF-8 CSV import of 2–5,000 measurements.
- Immutable data versions and saved analysis history backed by PostgreSQL.
- Identity, square, square-root, and reciprocal transforms on x, with an optional declared origin shift.
- Linear and quadratic ordinary least squares, free or fixed-zero intercept.
- Unit derivation for every coefficient, optional dimensional comparison to your claimed unit, standard errors, centered R², residuals, and canonical-unit charts.
- Specific rejection findings for invalid domains, insufficient observations, unidentifiable fits, unsafe temperature operations, and numerical limits.
- JSON exports containing raw data, settings, original results, version provenance, and SHA-256 checksums.
- Optional AI explanations of existing findings, with deterministic fallback when no provider is available.
- Project and workspace deletion; scheduled expiry cleanup.

## Fast local start

Install Docker Desktop (or Docker Engine with Compose) and Python 3, then run from this directory:

1. `python3 scripts/configure.py`
2. `docker compose up --build -d`
3. Open **http://localhost:3000**.

The migration runs before the API starts. Only the web service is exposed on the local machine. Keep `.env` private. `docker compose down` stops services and keeps the database volume. **Do not add `-v` unless you intend to erase the notebook.**

Native development and the optional Docker-free development database are explained in the run guide.

## A 30-second example

1. Open the default **Acceleration & time** sample. It is synthetic.
2. Keep **Square x**, **Linear**, and **Fix at zero**.
3. Select **Analyze measurements**.
4. The coefficient is approximately **0.021 m/s⁴**. Its unit is acceleration divided by time squared, not acceleration.
5. Inspect the unit mismatch and zero-intercept assumption findings. Switch to **Residuals** and export the result.

For a pure model `y = a x²`, square x and fit a linear model through zero. The quadratic-family model includes a linear term; fixing its intercept does not remove that term.

## Repository map

| Path | Purpose |
| --- | --- |
| `apps/web/` | Next.js interface, same-origin gateway, and CSP |
| `apps/api/src/lablens/` | Validated contracts, deterministic engine, PostgreSQL persistence, security, API |
| `apps/api/migrations/` | Frozen Alembic migration, SQL constraints, immutable-snapshot triggers, rule registry |
| `apps/api/tests/` | Numerical, property, input, security, and integration tests |
| `tests/browser/` | Playwright workflows and axe accessibility checks |
| `examples/` | Synthetic CSV fixtures and provenance notes |
| `compose.yaml`, `render.yaml` | Local and hosted deployment configuration |

## Verification

With Python 3.12 and Node 24 installed:

- Install Python dependencies from `requirements-dev.lock`, then install this package in editable mode without dependencies.
- Run `npm ci` and `npm run build`.
- Against an **isolated test database**, run `python scripts/verify.py --browser`.
- If native PostgreSQL is unavailable, run `python scripts/verify.py --local-db --browser`. This uses PGlite for local SQL/integration checks. It does not certify native PostgreSQL concurrency or production performance.

The GitHub Actions workflow runs the native PostgreSQL version. It has to execute in your repository before its status can be claimed green.

## Privacy, transparency, and scope

All bundled data is synthetic. Student reasoning, not generated conclusions, is the goal. Optional accounts and teacher sharing from the planning document remain outside this anonymous-workspace release; no placeholder controls advertise them.
