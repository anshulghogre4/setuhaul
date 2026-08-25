import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined

export const supabaseConfigured = Boolean(url && anon)

export const supabase: SupabaseClient | null = supabaseConfigured
  ? createClient(url!, anon!)
  : null

/** Two POC entry shells only. Operator and Admin both use `ops`. */
export type Portal = 'driver' | 'ops'

export const portalHome: Record<Portal, string> = {
  driver: '/driver',
  ops: '/ops',
}

export const portalLogin: Record<Portal, string> = {
  driver: '/driver/login',
  ops: '/ops/login',
}

const OPS_PORTAL_ROLES = new Set([
  'OPERATIONS_EXECUTIVE',
  'WAREHOUSE_PLANNER',
  'OPERATIONS_MANAGER',
  'FACILITY_MANAGER',
  'TRANSPORT_MANAGER',
  'REGIONAL_OPERATIONS_HEAD',
  'ADMIN',
])

export function roleToPortal(roleName: string): Portal | null {
  if (roleName === 'DRIVER') return 'driver'
  if (OPS_PORTAL_ROLES.has(roleName)) return 'ops'
  return null
}

export async function getSession(): Promise<Session | null> {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession()
  return data.session
}

export async function signIn(email: string, password: string) {
  if (!supabase) throw new Error('Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.')
  return supabase.auth.signInWithPassword({ email, password })
}

export async function signOut() {
  if (!supabase) return
  // E3.5 (issue #29): Supabase's signOut() defaults to `scope: 'global'`, which revokes every
  // refresh token for this user, not just this device. This is the plain single-device "Sign
  // Out" button, so it must say so explicitly -- without `local` here it silently becomes
  // sign_out_everywhere. Found live in production during E3.5's implementation: this call had
  // no scope argument at all, meaning every ordinary sign-out was already doing the global
  // revoke by accident.
  await supabase.auth.signOut({ scope: 'local' })
  sessionStorage.clear()
  localStorage.removeItem('setuhaul.returnUrl')
}
