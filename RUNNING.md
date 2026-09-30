# Running LabLens

LabLens is a web application with a Next.js frontend, a FastAPI service, and PostgreSQL storage. The numerical analysis works without an AI API key. The included datasets are synthetic.

## Requirements

- Docker Desktop with Docker Compose, running on your computer.
- Python 3 for generating a private local configuration.
- A browser and an available local port 3000.

Run the commands below from the repository root, the directory containing `compose.yaml`. On macOS, verify that `python3 --version`, `docker --version`, and `docker compose version` all work in your terminal. If `docker` is not found after installing Docker Desktop, start the application and reopen your terminal.

## Start with Docker Compose

1. Create a private `.env` file once:

   `python3 scripts/configure.py`

   The script generates random local credentials and deliberately refuses to overwrite an existing `.env`. If you already have one, keep it and continue. `.env.example` documents the available values; its placeholders are not working credentials.

2. Build and start the services:

   `docker compose up --build -d`

   On a first run, downloading and building images can take several minutes.

3. Inspect their status:

   `docker compose ps -a`

   The database and API should become healthy, `web` and `maintenance` should run, and the one-time `migrate` service should exit with code 0. If the web service starts before the others become healthy, wait briefly and check again.

4. Visit [http://localhost:3000](http://localhost:3000). Use `localhost` consistently because the default allowed origin is `http://localhost:3000`.

5. Open the synthetic **Acceleration & time** example and select **Analyze measurements**. With **Square x**, **Linear**, and **Fix at zero**, the coefficient should be close to **0.021 m/s⁴**. Inspect the unit and fixed-zero findings, view residuals, and download an export.

The application does not require a hosted AI provider. With `LABLENS_AI_API_KEY` empty, it presents deterministic explanations.

## Stop, restart, and inspect logs

- Stop and preserve the PostgreSQL volume: `docker compose down`.
- Restart: `docker compose up -d`.
- See service state: `docker compose ps -a`.
- Inspect startup errors: `docker compose logs --tail=100 api web migrate database`.
- Rebuild after source changes: `docker compose up --build -d`.

**Do not use `docker compose down -v` unless you intend to delete the local database volume.** Keep your `.env` file. Changing its password after the database volume is initialized will not change the existing PostgreSQL user's password.

Logs and exported files may contain lab measurements. Keep private data out of shared issue reports.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `zsh: command not found: docker` | Install and launch Docker Desktop, then reopen VS Code's terminal and run `docker --version`. |
| Docker daemon is unavailable | Launch Docker Desktop and wait for its engine to finish starting. |
| `configure.py` says `.env` already exists | This is intentional; proceed with the existing configuration. |
| Port 3000 is occupied | Stop the conflicting process, then retry. The default origin assumes `localhost:3000`. |
| Migration or API is unhealthy | Run `docker compose ps -a` and inspect `docker compose logs --tail=100 db migrate api`. |
| Page loads but writes fail | Open `http://localhost:3000` exactly and verify `LABLENS_PUBLIC_ORIGIN` in `.env` matches it. |

For PostgreSQL authentication failures with an existing database volume, preserve the volume and check that `.env` still contains the password used when it was initialized. Do not erase a volume as a first troubleshooting step.

## Native development without Docker

The supported development versions are Python 3.12 and Node.js 24. Native development also needs PostgreSQL 18, or the local PGlite development helper described below.

1. Create and activate a Python environment: `python3 -m venv .venv` and `source .venv/bin/activate`.
2. Install Python dependencies and package: `python -m pip install --require-hashes -r requirements-dev.lock` and `python -m pip install --no-deps -e .`.
3. Install JavaScript dependencies: `npm ci`.
4. Set `LABLENS_DATABASE_URL` to a disposable PostgreSQL database using `postgresql+psycopg://`. Set `LABLENS_PUBLIC_ORIGIN=http://localhost:3000` and `LABLENS_API_URL=http://127.0.0.1:8000` for the web process. The Python app reads the root `.env`; the web process reads its environment and `apps/web/.env.local`. If setting `LABLENS_GATEWAY_SECRET`, both processes must use the same value. Docker Compose configures these values for you.
5. Run `alembic upgrade head`.
6. Start the API: `uvicorn lablens.main:app --host 127.0.0.1 --port 8000 --no-access-log`.
7. In a second terminal, run `npm run dev` and open [http://localhost:3000](http://localhost:3000).

For a Docker-free local development database, `npm run db:local` starts PGlite on `127.0.0.1:5432`, storing files under `.local-data/postgres`. Use `LABLENS_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres` and `LABLENS_POOL_SIZE=1`. This helper listens only on loopback and is not suitable for public hosting or concurrency validation.

## Run checks

With the development dependencies installed, and with a **separate disposable test database**:

1. `ruff check apps/api scripts`
2. `npm run typecheck`
3. `npm run build`
4. `python scripts/verify.py --browser` against native PostgreSQL, or `python scripts/verify.py --local-db --browser` with the documented local helper.

Browser tests require Playwright Chromium. On macOS or Windows, install it with `npx playwright install chromium` and set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable if the test runner needs an explicit path. The GitHub Actions workflow runs browser tests on Linux with native PostgreSQL.

For deployment requirements, backup and restore procedures, and release checks, see [docs/OPERATIONS.md](docs/OPERATIONS.md) and [docs/RELEASE_STATUS.md](docs/RELEASE_STATUS.md). A successful local start does not establish that a public deployment or production validation has been completed.
