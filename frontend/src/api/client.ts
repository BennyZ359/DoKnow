/**
 * Minimal typed HTTP client for the DoKnow backend.
 *
 * Error contract (see backend/app/api/routers/__init__.py):
 *   non-2xx bodies are `{ "error": str, "message": str, "findings"?: [...] }`.
 * We surface `message` to the UI and keep `error`/`findings` on the thrown ApiError.
 */

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, '') ??
  'http://localhost:8000'

const TOKEN_KEY = 'doknow_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly findings?: unknown[]

  constructor(status: number, code: string, message: string, findings?: unknown[]) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.findings = findings
  }
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined>
  headers?: Record<string, string>
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(API_BASE_URL + path)
  if (options.query) {
    for (const [k, v] of Object.entries(options.query)) {
      if (v !== undefined && v !== '') url.searchParams.set(k, String(v))
    }
  }

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...options.headers,
  }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    // Let the browser set the multipart boundary; do NOT force Content-Type.
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  let res: Response
  try {
    res = await fetch(url.toString(), {
      method: options.method ?? 'GET',
      headers,
      body,
    })
  } catch {
    throw new ApiError(
      0,
      'NetworkError',
      `无法连接后端服务（${API_BASE_URL}）：请先启动后端，例如 docker compose up --build，或本地运行 uvicorn`,
    )
  }

  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) {
    if (res.status === 401) onUnauthorized?.()
    const detail = (data as { detail?: { error?: string; message?: string; findings?: unknown[] } })?.detail
    const code = detail?.error ?? `HTTP_${res.status}`
    const message = detail?.message ?? (typeof data === 'string' ? data : `请求失败 (${res.status})`)
    throw new ApiError(res.status, code, message, detail?.findings)
  }

  return data as T
}

export const http = {
  get: <T>(path: string, query?: RequestOptions['query']) => request<T>(path, { method: 'GET', query }),
  post: <T>(path: string, body?: unknown, query?: RequestOptions['query']) =>
    request<T>(path, { method: 'POST', body, query }),
  patch: <T>(path: string, body?: unknown, query?: RequestOptions['query']) =>
    request<T>(path, { method: 'PATCH', body, query }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string, query?: RequestOptions['query']) =>
    request<T>(path, { method: 'DELETE', query }),
}
