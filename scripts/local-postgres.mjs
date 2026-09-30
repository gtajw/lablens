// Development fallback only. Production and CI use a native PostgreSQL service.
import { PGlite } from '@electric-sql/pglite';
import { PGLiteSocketServer } from '@electric-sql/pglite-socket';
import { mkdir } from 'node:fs/promises';

await mkdir('.local-data', { recursive: true });
const db = await PGlite.create(process.env.LABLENS_PGLITE_PATH || '.local-data/postgres');
const server = new PGLiteSocketServer({ db, host: '127.0.0.1', port: Number(process.env.LABLENS_DB_PORT || 5432), maxConnections: 20 });
await server.start();
console.log('Local development PostgreSQL (PGlite) listening on 127.0.0.1:5432. No network authentication; loopback only.');
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, async () => { await server.stop(); await db.close(); process.exit(0); });
