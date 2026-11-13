// Thin typed fetch wrapper. Every call hits the real backend — never a
// fabricated response. A non-2xx response is thrown as `ApiError`, whose
// shape callers read directly from the backend's documented
// `{"error": {"code","message","field"}}` contract rather than a
// generic "something went wrong" string.

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {
  code: string;
  field: string | null;
  status: number;

  constructor(status: number, code: string, message: string, field: string | null) {
    super(message);
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch {
    throw new ApiError(0, 'network_error', `Unable to reach the API at ${API_BASE}${path}`, null);
  }

  if (!res.ok) {
    let code = 'unknown_error';
    let message = `Request failed with status ${res.status}`;
    let field: string | null = null;
    try {
      const body = await res.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        field = body.error.field ?? null;
      }
    } catch {
      // response body wasn't JSON - keep the generic message above
    }
    throw new ApiError(res.status, code, message, field);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function get<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const query = params
    ? '?' +
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== '')
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join('&')
    : '';
  return request<T>(`${path}${query}`);
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
}

export { API_BASE };
