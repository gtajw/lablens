# Release status — LabLens 1.0 release candidate

Evidence updated September 27, 2026. **The application is implemented and locally verified; it is not yet certified for a public production rollout or submitted to the hackathon.** The original strict Definition of Done remains binding for that stronger claim.

## Completed evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Backend tests | 109 passed, zero skipped in the integration run | `test-results.xml` |
| Browser tests | 6 passed | `browser-results.json` |
| TypeScript and production web build | Passed | Reproduce with `npm run typecheck` and `npm run build` |
| Python lint | Passed | `ruff check apps/api scripts` |
| Automated accessibility | No violations in the tested desktop/mobile states and rule tags | Browser report; not full WCAG certification |
| Production dependency audits | Zero reported vulnerabilities in the captured installed-package audits | `npm-audit.json`, `python-audit.json`; advisories can lag |
| Persistence and access isolation | Covered by integration tests with PostgreSQL-compatible PGlite | Native-host testing remains below |
| Provider failures | Success, invalid output, HTTP failures, timeout, size and elapsed-time cases passed with mock provider | `test_explanations.py`; no live credential used |

## Coverage, stated without conflating line and branch measures

| Module | Line coverage | Branch coverage |
| --- | ---: | ---: |
| `__init__.py` | 100.0% | No branches |
| `contracts.py` | 92.6% | 66.7% |
| `csv_import.py` | 91.9% | 81.2% |
| `db.py` | 100.0% | No branches |
| `engine.py` | 97.2% | 93.2% |
| `errors.py` | 100.0% | No branches |
| `explanations.py` | 100.0% | 100.0% |
| `main.py` | 92.7% | 90.6% |
| `repository.py` | 95.2% | 75.0% |
| `security.py` | 97.9% | 93.8% |
| `settings.py` | 85.7% | 50.0% |
| `units.py` | 100.0% | 100.0% |

The original 95% numerical branch, 90% application branch, 90% mutation-score, and 80% frontend branch gates are **not all established**. In particular, mutation scoring and frontend branch instrumentation have not been run. End-to-end tests do not substitute for those thresholds. Do not describe an overall combined coverage percentage as branch coverage.

## Outstanding release gates

| Gate | Required action | Why it is not marked complete |
| --- | --- | --- |
| Next.js security patch | Review the September 30 advisory, install the available patched release, and rerun the complete checks | Current pinned 16.3.6 precedes the announced security release |
| Native database and concurrency | Run CI with PostgreSQL 18; exercise simultaneous retries, deletion races, termination, locks and pool saturation | Local PGlite is not a multi-process production database |
| Docker/Render deployment | Build both images, validate the Blueprint on Render, and smoke-test HTTPS cookies, private networking and migrations | No Docker daemon or authenticated hosting deployment used here |
| Least-privilege database roles | Separate migration ownership from runtime privileges and test denial of DDL/trigger changes | Bootstrap template uses owner credentials |
| Backup/restore and deletion | Configure retention, rehearse isolated restore and deletion reconciliation, update the privacy page | Requires the actual operator and managed database |
| Load and capacity | Meet every target in the original DoD on the real resource plan; add edge bootstrap abuse controls | No production-host load evidence |
| Original verification thresholds | Complete remaining branch and mutation requirements; fully validate/generated response contracts | See coverage table and ADR |
| Human accessibility | Keyboard and screen-reader review across real browsers/devices | Automated axe checks are a limited subset |
| Scientific/educational review | Teacher review, all original demo scenarios, and a permission-based pilot | No classroom impact claim has been established |
| Submission | Confirm team names/eligibility/permissions, public links, AI disclosure and actual Devpost submission | These decisions belong to the team |

## Security advisory reference

Next.js announced a September 30, 2026 security release, with planned 16.3.7/15.5.27 fixes including critical/high issues. A clean audit today does not waive this gate. Source: https://nextjs.org/blog/upcoming-nextjs-security-release-september-2026 (checked September 27). The exact affected paths and final upgrade instructions must be reviewed when published.

## Environment and scope

Python 3.12.14, Node 24.19.0, Chromium 153, exact package versions in lockfiles. Local verification runs an isolated PGlite PostgreSQL adapter plus the real API and production-built Next.js server. All bundled measurements are synthetic. A non-failing Starlette warning notes eventual TestClient migration from HTTPX; it does not change the test result.

No real student data, public hosting, paid resource provisioning, award opt-in, consent, or hackathon submission was performed. See `../HOW_TO_RUN_AND_SUBMIT.md` for concrete next steps.
