export class ApiError extends Error {
  constructor(message: string, public code: string, public status: number, public requestId?: string) { super(message); }
}
let csrf = '';
export const setCsrf = (value: string) => { csrf = value; };

export async function api<T>(path: string, options: { method?: string; data?: unknown; key?: string; signal?: AbortSignal } = {}): Promise<T> {
  const method = options.method || 'GET';
  const headers: Record<string, string> = {};
  if (method !== 'GET') { headers['X-CSRF-Token'] = csrf; headers['Idempotency-Key'] = options.key || crypto.randomUUID(); }
  const form = options.data instanceof FormData;
  if (method !== 'GET' && !form) headers['Content-Type'] = 'application/json';
  let response: Response;
  try {
    response = await fetch('/api/v1' + path, { method, credentials: 'same-origin', cache: 'no-store', headers,
      body: method === 'GET' ? undefined : form ? options.data as FormData : JSON.stringify(options.data ?? {}), signal: options.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('Connection interrupted. Reconnect and retry; your saved results are unchanged.', 'NETWORK_ERROR', 0);
  }
  if (response.status === 204) return undefined as T;
  let body;
  try { body = await response.json(); } catch { throw new ApiError('The service returned an unexpected response. Please retry.', 'RESPONSE_INVALID', response.status); }
  if (!response.ok) {
    const fields = body.error?.field_errors?.map((f: { message: string }) => f.message).join(' ');
    throw new ApiError(fields || body.error?.message || 'The request failed.', body.error?.code || 'REQUEST_FAILED', response.status, body.request_id);
  }
  return body.data as T;
}

export function downloadJson(filename: string, contentJson: string, sha256: string) {
  // Keep Python's exact canonical numeric lexemes; JSON.parse/stringify changes SHA-256 bytes.
  const bytes = `{"content":${contentJson},"sha256":"${sha256}"}`;
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
