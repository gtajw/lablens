# LabLens operations and production release checklist

## Trust boundaries and secrets

Only the web gateway is public. Keep FastAPI and PostgreSQL private. The web and API share a random gateway secret of at least 48 characters; the assertion is short-lived and binds method, path/query, body, session, CSRF, content type, and idempotency key. Do not trust client-supplied forwarding headers. The browser receives only a Secure/HttpOnly/SameSite=Strict cookie and a CSRF value. HTTPS is required in production.

The Render template bootstraps with the managed database owner connection. Before real-user rollout, provision a separate runtime role with only CONNECT, schema USAGE, required table SELECT/INSERT/UPDATE/DELETE, and sequence USAGE/SELECT. Give migration ownership/DDL privileges only to the migration task. Keep the runtime role neither superuser nor schema owner; revoke CREATE on the public schema. The runtime must not alter tables, triggers, functions, or rules. Because owner credentials are currently used by preDeployCommand, separating roles also requires moving migrations to a separately credentialed release task. Test allowed operations and explicit DDL/trigger-disable denial with the runtime account. This is an operator release gate, not automatically completed by the template.

Do not log request bodies, CSV text, authorization assertions, cookies, session tokens, or provider keys. The supplied API starts without access logs and records minimal application events. Configure reverse-proxy/platform logs with the same privacy policy. Keep logs access-controlled; remove accidental sensitive values promptly.

## Backups, restore, and deletion

1. Enable encrypted managed PostgreSQL backups. Record an explicit retention period and publish it in the privacy page before inviting real users.
2. Take a custom-format PostgreSQL backup using a dedicated backup role and a secure connection. Keep credentials out of command history and command-line arguments; use the platform's secret injection or a protected password file.
3. Restore into a new isolated database. Run migration-state inspection, integrity checks, and synthetic smoke tests. Never restore over the live database as a test.
4. Document the measured recovery time and recoverable point. The product has no proven RPO/RTO until this exercise is done.
5. Run `python scripts/cleanup.py` hourly. Session/principal expiry is absolute; cleanup marks projects for deletion and cascades snapshots. Idempotency and rate records expire separately; audit retention is 90 days and failed AI records 7 days.
6. Alert on cleanup failure. Expired sessions are denied immediately even if cleanup is delayed. Deletion from the active database does not immediately remove older backups. Restoring a backup can resurrect previously deleted data; keep the restored service isolated, rerun expiry cleanup, and reconcile deletions before reopening. A robust deletion ledger outside restored backups is a further production requirement if users rely on that guarantee.

## Deployment and rollback

Run locked dependency installation, lint, type checks, production build, native-PostgreSQL tests, browser tests, and dependency audits before deploying. Apply forward migrations through a controlled release step. The initial migration intentionally has no destructive automatic downgrade. For a failed application deployment, roll back the application only if its schema is compatible. For a schema incident, restore into a new database and validate before switching traffic.

The Docker and Render manifests are supplied but have not been deployed or built in a Docker-capable environment here. Validate them on the chosen host. Limit web/API instances and database connections to the purchased capacity; each API process has its own pool. Two workers with pool_size=5 can consume ten base connections plus any overflow permitted by the pool configuration. Account for migrations, cleanup, monitoring, and concurrent deployments.

## Monitoring and abuse limits

Monitor health latency, 5xx rates, 429 counts, DB connection use, lock waits, storage growth, cleanup success, and provider timeout rates without recording source measurements. Rate limits are atomic and shared via PostgreSQL. Per-session limits do not stop an attacker from creating new anonymous sessions; add edge-level bootstrap throttling and overall storage/budget ceilings before a public launch. The global bootstrap limit trades availability for bounded growth and should be assessed under realistic traffic.

Only configured HTTPS AI provider URLs are accepted. Use minimal scoped credentials, budget limits, and server-side environment variables. Provider calls have connect/read timeouts, a 32 KiB output limit, and elapsed-time checks; the elapsed check occurs between reads, so a final blocked read can add up to its read timeout. Disable inference during incidents. Core numerical analysis remains available.

## Required performance exercise on the actual host

Use a disposable deployment and synthetic data with separate authenticated sessions. Measure warm and cold behavior separately and record hardware, worker count, pool sizes, row counts, concurrency, duration, p50/p95, errors, and peak pool usage. Test 20 concurrent project sessions, 10 simultaneous 100-row uploads, 10 simultaneous 1,000-row quadratic analyses, and five 5,000-row analyses. Verify the latency/pool targets in `docs/blueprint/05-definition-of-done.md`. Verify simultaneous same-key retries commit one analysis, different payloads conflict, deletion racing analysis cannot leave orphans, and process termination rolls back incomplete mutations.

PGlite tests exercise PostgreSQL SQL behavior locally but do not substitute for native PostgreSQL locks, multi-process concurrency, backup restore, or real-host load tests. The CI workflow uses native PostgreSQL; a successful remote workflow run has not been claimed.

## Incident response

Disable public writes or remove public access if authorization, data integrity, or privacy is in question. Preserve minimal diagnostic evidence, rotate exposed secrets, assess affected data, and follow the operator's applicable notification obligations. Never claim a clean audit proves no compromise. After a numerical defect, increment the engine/rule version and preserve old snapshots; reruns must create new linked results rather than rewrite history.
