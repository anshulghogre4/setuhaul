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

export function roleToPortal(roleName: string): Portal | null {
  if (roleName === 'DRIVER') return 'driver'
  if (roleName === 'OPERATIONS_EXECUTIVE' || roleName === 'ADMIN') return 'ops'
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
  await supabase.auth.signOut()
  sessionStorage.clear()
  localStorage.removeItem('setuhaul.returnUrl')
}
