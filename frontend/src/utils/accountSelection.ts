import type { Account } from '@/types'
import { sessionUser } from '@/utils/frappeSession'

const ACCOUNT_KEY = 'nudg.selected_account'

function storageKey() {
  const user = sessionUser()
  return user ? `${ACCOUNT_KEY}:${user}` : ACCOUNT_KEY
}

/** The number this user last chose. Null until they change the dropdown. */
export function readSavedAccount(): string | null {
  try {
    const value = localStorage.getItem(storageKey())
    return value || null
  } catch {
    return null
  }
}

export function writeSavedAccount(name: string) {
  try {
    localStorage.setItem(storageKey(), name || 'all')
  } catch {
    /* ignore quota / private mode */
  }
}

/**
 * Keep a saved choice across refresh.
 * With nothing saved, use the user's assigned number (the default one when they
 * have several). Someone with no assigned number stays on All numbers.
 */
export function chooseAccount(accounts: Account[], saved: string | null): string {
  const names = new Set(accounts.map((row) => row.name))
  if (saved === 'all') return 'all'
  if (saved && names.has(saved)) return saved
  const assigned = accounts.filter((row) => row.assigned)
  if (!assigned.length) return 'all'
  return (assigned.find((row) => row.is_default) || assigned[0]).name
}
