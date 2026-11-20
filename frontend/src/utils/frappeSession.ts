/** User, roles, and display names from the Frappe boot payload, then the Nudg page boot. */

export function sessionUser(): string {
  const fromSession = window.frappe?.session?.user
  if (typeof fromSession === 'string' && fromSession && fromSession !== 'Guest') return fromSession
  return typeof window !== 'undefined' && window.user ? window.user : ''
}

export function sessionRoles(): string[] {
  const bootRoles = window.frappe?.boot?.user?.roles
  if (Array.isArray(bootRoles) && bootRoles.length) {
    return bootRoles.filter((role): role is string => typeof role === 'string')
  }
  return Array.isArray(window.roles) ? window.roles : []
}

export function userLabel(user?: string | null): string {
  if (!user) return 'Unassigned'
  const info = window.frappe?.boot?.user_info?.[user]
  const full = info?.fullname || info?.full_name
  if (typeof full === 'string' && full.trim()) return full.trim()
  const local = user.split('@')[0] || user
  return local.replace(/[._]/g, ' ')
}
