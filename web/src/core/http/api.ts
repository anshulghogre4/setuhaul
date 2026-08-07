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

export async function apiGet<T>(path: string): Promise<ApiEnvelope<T>> {
  const session = await getSession()
  if (!session?.access_token) {
    throw new Error('Not authenticated')
  }
  const res = await fetch(`${apiBase}${path}`, {
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      Accept: 'application/json',
    },
  })
  const body = (await res.json()) as ApiEnvelope<T>
  if (!res.ok || !body.success) {
    const detail = body.errors?.[0]?.detail || body.message || res.statusText
    throw new Error(detail)
  }
  return body
}
