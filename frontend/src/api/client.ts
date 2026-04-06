import { toast } from "sonner"

const BASE_URL = "/api"

// Paths that should not include the Authorization header
const PUBLIC_PATHS = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/google", "/auth/forgot-password", "/auth/reset-password", "/auth/verify-email"]

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }
}

// --- Token management ---

export function getAccessToken(): string | null {
  return localStorage.getItem("access_token")
}

export function getRefreshToken(): string | null {
  return localStorage.getItem("refresh_token")
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem("access_token", access)
  localStorage.setItem("refresh_token", refresh)
}

export function clearTokens(): void {
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
}

// --- Refresh mutex ---

let refreshPromise: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) {
    return refreshPromise
  }

  refreshPromise = (async () => {
    const rt = getRefreshToken()
    if (!rt) return false

    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      })
      if (!res.ok) return false
      const data = await res.json()
      setTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      return false
    }
  })()

  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}

// --- Auth headers ---

function authHeaders(path: string): Record<string, string> {
  if (PUBLIC_PATHS.some((p) => path.startsWith(p))) return {}
  const token = getAccessToken()
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

// --- Response handler with 401 retry ---

async function handleResponse<T>(response: Response, retryFn?: () => Promise<Response>, path?: string): Promise<T> {
  const isPublic = path && PUBLIC_PATHS.some((p) => path.startsWith(p))

  if (response.status === 401 && retryFn && !isPublic) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      const retryRes = await retryFn()
      return handleResponse<T>(retryRes)
    }
    // Refresh failed -- clear tokens and redirect to login
    clearTokens()
    if (window.location.pathname !== "/login") {
      window.location.href = "/login"
    }
    throw new ApiError(401, "Session expired")
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    const detail = body.detail ?? response.statusText
    if (!isPublic) toast.error(`${response.status}: ${detail}`)
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export async function get<T>(path: string): Promise<T> {
  const doFetch = () => fetch(`${BASE_URL}${path}`, { headers: authHeaders(path) })
  const res = await doFetch()
  return handleResponse<T>(res, doFetch, path)
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(path) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  const res = await doFetch()
  return handleResponse<T>(res, doFetch, path)
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE_URL}${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders(path) },
      body: JSON.stringify(body),
    })
  const res = await doFetch()
  return handleResponse<T>(res, doFetch, path)
}

export async function patch<T>(path: string, body: unknown): Promise<T> {
  const doFetch = () =>
    fetch(`${BASE_URL}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders(path) },
      body: JSON.stringify(body),
    })
  const res = await doFetch()
  return handleResponse<T>(res, doFetch, path)
}

export async function del<T = { detail: string }>(path: string): Promise<T> {
  const doFetch = () => fetch(`${BASE_URL}${path}`, { method: "DELETE", headers: authHeaders(path) })
  const res = await doFetch()
  return handleResponse<T>(res, doFetch, path)
}

export async function upload<T>(path: string, file: File, fieldName = "file"): Promise<T> {
  const doFetch = () => {
    const form = new FormData()
    form.append(fieldName, file)
    return fetch(`${BASE_URL}${path}`, {
      method: "POST",
      headers: authHeaders(path),
      body: form,
    })
  }
  const res = await doFetch()
  return handleResponse<T>(res, doFetch, path)
}
