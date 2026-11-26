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
    if (!value || value === 'all') return null
    return value
  } catch {
    return null
  }
}

export function writeSavedAccount(name: string) {
  try {
    if (!name || name === 'all') {
      localStorage.removeItem(storageKey())
      return
    }
    localStorage.setItem(storageKey(), name)
  } catch {
    /* ignore quota / private mode */
  }
}

/**
 * Always pick exactly one WhatsApp account.
 * Prefer the saved choice when still allowed, else the assigned default,
 * else the first assigned (or first visible) number. Empty string when none.
 */
export function chooseAccount(accounts: Account[], saved: string | null): string {
  const names = new Set(accounts.map((row) => row.name))
  const remembered = saved && saved !== 'all' ? saved : null
  if (remembered && names.has(remembered)) return remembered

  const assigned = accounts.filter((row) => row.assigned)
  const pool = assigned.length ? assigned : accounts
  if (!pool.length) return ''
  return (pool.find((row) => row.is_default) || pool[0])!.name
}

/** Concrete account for API calls; undefined when none is selected. */
export function accountArg(account: string | null | undefined): string | undefined {
  if (!account || account === 'all') return undefined
  return account
}

/** Same label the top-bar number dropdown shows. */
export function labelForAccount(
  accounts: Array<{ name: string; account_name?: string }>,
  account: string | null | undefined,
): string {
  const name = accountArg(account)
  if (!name) return ''
  const match = accounts.find((row) => row.name === name)
  return match?.account_name || name
}
