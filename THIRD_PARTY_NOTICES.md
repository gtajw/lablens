# Resources, software, and attribution

LabLens application source is offered under the included MIT license. Dependencies retain their own licenses and notices; that license does not relicense them. Exact versions and integrity hashes are in `package-lock.json`, `requirements.lock`, and `requirements-dev.lock`.

## Major resources

| Resource | Role | Upstream |
| --- | --- | --- |
| Next.js / React / TypeScript | Web framework, UI, static checking | https://nextjs.org/ ; https://react.dev/ ; https://www.typescriptlang.org/ |
| Lucide | Interface icons | https://lucide.dev/ |
| FastAPI / Starlette / Pydantic | HTTP and validation | https://fastapi.tiangolo.com/ ; https://www.starlette.io/ ; https://docs.pydantic.dev/ |
| Uvicorn | ASGI server | https://www.uvicorn.org/ |
| SQLAlchemy / Alembic / psycopg | Persistence and migrations | https://www.sqlalchemy.org/ ; https://alembic.sqlalchemy.org/ ; https://www.psycopg.org/ |
| PostgreSQL | Production database target | https://www.postgresql.org/ |
| Pint | Unit algebra and conversion | https://pint.readthedocs.io/ |
| NumPy / SciPy | Numerical arrays and SVD least squares | https://numpy.org/ ; https://scipy.org/ |
| HTTPX / PyJWT | Provider HTTP and signed gateway assertions | https://www.python-httpx.org/ ; https://pyjwt.readthedocs.io/ |
| pytest / Hypothesis / Ruff / pip-audit | Python verification | https://docs.pytest.org/ ; https://hypothesis.readthedocs.io/ ; https://docs.astral.sh/ruff/ ; https://github.com/pypa/pip-audit |
| Playwright / axe-core | Browser and automated accessibility tests | https://playwright.dev/ ; https://github.com/dequelabs/axe-core |
| PGlite and pglite-socket | Embedded local PostgreSQL verification | https://pglite.dev/ |
| @sparticuz/chromium | Test-only Chromium distribution | https://github.com/Sparticuz/chromium |
| openapi-typescript | Generated TypeScript request types | https://openapi-ts.dev/ |
| Docker / Render / GitHub Actions | Supplied deployment and CI configuration | https://www.docker.com/ ; https://render.com/ ; https://github.com/features/actions |
| Featherless-compatible API | Optional hosted explanation provider; not called with live credentials in this build | https://featherless.ai/ |
| OpenAI ChatGPT/Codex | AI-assisted research, code, tests, debugging, and documentation | https://openai.com/ |

## Data, design, and documentation

Sample measurements are synthetic and app-authored. No external research dataset or real student record is included. Earlier project research and design files are preserved in `docs/research/` and `docs/blueprint/`; disclose their timing. Screenshots come from the working app. The interface is custom CSS with Lucide icons and a simple app-authored vector mark. No stock photo, purchased template, or externally copied lab report is used.

Reference documentation consulted includes Pint offset-temperature behavior, SciPy `linalg.lstsq`, PGlite's socket adapter, Render's Blueprint specification, and Next.js security announcements. Documentation informs implementation; it does not certify correctness or event eligibility.

## Sponsor claims

Render deployment files and optional Featherless-compatible integration are included. Momen, n8n, Backboard, KnowledgeOwl, Boot.dev, and Gen.xyz are not integrated into the delivered app. Do not claim use or redemption of sponsor benefits merely because they were listed in the event brief. Optional domain/hosting/AI accounts remain subject to their eligibility and terms.
