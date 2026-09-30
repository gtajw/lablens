import { createHash, createHmac, randomUUID } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
const maxBody = 2_097_152;
const sha = (value: string | Buffer) => createHash('sha256').update(value).digest('hex');

async function gateway(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const requestId = randomUUID();
  const fail = (status: number, code: string, message: string) => NextResponse.json({ request_id: requestId,
    error: { code, message, retryable: status === 503, field_errors: [] } }, { status, headers: { 'Cache-Control': 'no-store', 'X-Request-ID': requestId } });
  const production = process.env.LABLENS_ENVIRONMENT === 'production';
  const secret = process.env.LABLENS_GATEWAY_SECRET || (production ? '' : 'local-development-only-change-this-secret');
  if (secret.length < (production ? 48 : 32)) return fail(503, 'SERVICE_NOT_CONFIGURED', 'The service is being configured. Try again shortly.');
  const { path } = await context.params;
  if (!path.every(p => /^[a-z0-9-]+$/.test(p))) return fail(404, 'RESOURCE_NOT_FOUND', 'This endpoint does not exist.');
  const origin = process.env.LABLENS_PUBLIC_ORIGIN || (production ? '' : request.nextUrl.origin);
  if (!origin) return fail(503, 'SERVICE_NOT_CONFIGURED', 'The service is being configured.');
  const mutating = !['GET', 'HEAD'].includes(request.method);
  // Bootstrap also creates a cookie: reject cross-site subresource requests.
  if (request.headers.get('sec-fetch-site') === 'cross-site' ||
      (mutating && request.headers.get('origin') !== origin)) return fail(403, 'ORIGIN_INVALID', 'Open LabLens directly and try again.');
  let body: Buffer;
  try {
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (reader) while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.length;
      if (size > maxBody) { await reader.cancel(); return fail(413, 'PAYLOAD_TOO_LARGE', 'Files must be 1 MiB or smaller.'); }
      chunks.push(chunk.value);
    }
    body = Buffer.concat(chunks);
  } catch { return fail(400, 'REQUEST_INVALID', 'The request could not be read. Please retry.'); }
  const cookieName = production ? '__Host-lablens' : 'lablens';
  const token = request.cookies.get(cookieName)?.value || '';
  const csrf = request.headers.get('x-csrf-token') || '';
  const internalPath = '/internal/v1/' + path.join('/') + request.nextUrl.search;
  const timestamp = Math.floor(Date.now() / 1000);
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
  const claims = Buffer.from(JSON.stringify({ iss: 'lablens-web', aud: 'lablens-api', iat: timestamp, exp: timestamp + 30,
    method: request.method, path: internalPath, body: sha(body), session: sha(token), csrf: sha(csrf), idempotency: sha(request.headers.get('idempotency-key') || ''), content_type: sha(request.headers.get('content-type') || '') })).toString('base64url');
  const signature = createHmac('sha256', secret).update(header + '.' + claims).digest('base64url');
  const headers: Record<string, string> = { 'X-Gateway-Assertion': `${header}.${claims}.${signature}`, 'X-Session-Token': token, 'X-CSRF-Token': csrf };
  for (const name of ['content-type', 'idempotency-key']) {
    const value = request.headers.get(name);
    if (value) headers[name] = value;
  }
  try {
    const endpoint = (process.env.LABLENS_API_URL || (process.env.LABLENS_API_HOSTPORT ? `http://${process.env.LABLENS_API_HOSTPORT}` : 'http://127.0.0.1:8000')).replace(/\/$/, '') + internalPath;
    const upstream = await fetch(endpoint, { method: request.method, headers, body: mutating ? new Uint8Array(body) : undefined,
      cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(20000) });
    const output = new Headers({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    for (const name of ['content-type', 'x-request-id', 'retry-after']) {
      const value = upstream.headers.get(name);
      if (value) output.set(name, value);
    }
    const response = new NextResponse(upstream.status === 204 ? null : upstream.body, { status: upstream.status, headers: output });
    const fresh = upstream.headers.get('x-new-session');
    if (fresh) response.cookies.set(cookieName, fresh, { httpOnly: true, secure: production, sameSite: 'strict', path: '/', maxAge: 30 * 86400 });
    if (upstream.headers.has('x-clear-session')) response.cookies.set(cookieName, '', { httpOnly: true, secure: production, sameSite: 'strict', path: '/', maxAge: 0 });
    return response;
  } catch { return fail(503, 'SERVICE_UNAVAILABLE', 'LabLens could not reach storage. The request may not have completed; please retry.'); }
}
export { gateway as GET, gateway as POST, gateway as PATCH, gateway as DELETE };
