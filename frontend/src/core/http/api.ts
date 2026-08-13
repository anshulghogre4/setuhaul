import { getSession } from '../auth/supabase'

const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || 'http://localhost:8000'

export type ApiEnvelope<T> = {
  success: boolean
  message: string
  data: T
  timestamp: string
  request_id: string
  errors?: Array<{ code: string; detail: string; field?: string }>
}

export type MeProfile = {
  user_id: string
  email: string
  full_name: string
  role_id: string
  role_name: string
  driver_id: string | null
  facility_id: string | null
  permissions: string[]
  scope: { type: string; facility_id: string | null; driver_id: string | null }
}

async function authHeaders(extra?: HeadersInit): Promise<HeadersInit> {
  const session = await getSession()
  if (!session?.access_token) {
    throw new Error('Not authenticated')
  }
  return {
    Authorization: `Bearer ${session.access_token}`,
    Accept: 'application/json',
    ...extra,
  }
}

export async function apiGet<T>(path: string): Promise<ApiEnvelope<T>> {
  const res = await fetch(`${apiBase}${path}`, {
    headers: await authHeaders(),
  })
  const body = (await res.json()) as ApiEnvelope<T>
  if (!res.ok || !body.success) {
    const detail = body.errors?.[0]?.detail || body.message || res.statusText
    throw new Error(detail)
  }
  return body
}

export async function apiPost<T>(
  path: string,
  payload: unknown,
  opts?: { idempotencyKey?: string },
): Promise<ApiEnvelope<T>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (opts?.idempotencyKey) {
    headers['Idempotency-Key'] = opts.idempotencyKey
  }
  const res = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: await authHeaders(headers),
    body: JSON.stringify(payload),
  })
  const body = (await res.json()) as ApiEnvelope<T>
  if (!res.ok || !body.success) {
    const detail = body.errors?.[0]?.detail || body.message || res.statusText
    throw new Error(detail)
  }
  return body
}

export function formatUserFriendlyError(err: unknown): string {
  if (!err) return 'Something went wrong while processing your request. Please try again.'
  const message = err instanceof Error ? err.message : String(err)
  const lower = message.toLowerCase()

  if (
    lower.includes('failed to fetch') ||
    lower.includes('networkerror') ||
    lower.includes('network error') ||
    lower.includes('failed to connect') ||
    lower.includes('load failed')
  ) {
    return 'Unable to connect to SetuHaul server. Please check your internet connection or server status and try again.'
  }
  if (lower.includes('not authenticated') || lower.includes('401') || lower.includes('unauthorized') || lower.includes('token expired')) {
    return 'Your session has expired. Please sign in again.'
  }
  if (lower.includes('403') || lower.includes('forbidden') || lower.includes('permission')) {
    return 'Access denied. You do not have permission for this action.'
  }
  if (lower.includes('404') || lower.includes('not found')) {
    return 'The requested record or facility details could not be found.'
  }
  if (lower.includes('409') || lower.includes('conflict')) {
    return 'This request has already been processed or updated by another user. Please refresh and try again.'
  }
  if (lower.includes('500') || lower.includes('502') || lower.includes('503') || lower.includes('504')) {
    return 'SetuHaul server is temporarily busy. Please try again in a few moments.'
  }
  const cleaned = message.replace(/^(error:|apperror:|httperror:)\s*/i, '').trim()
  return cleaned || 'An unexpected error occurred. Please try again.'
}
