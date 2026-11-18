import type { Account } from '@/types'

/** frappe-ui persists `createResource({ cache })` in IndexedDB under a shared key. */
const LEGACY_CACHE_KEYS = ['["nudg:inbox"]', '["nudg:thread"]', '["nudg:logs"]']

export function deskCacheKey(bucket: 'inbox' | 'thread' | 'logs') {
  const user = typeof window !== 'undefined' && window.user ? window.user : 'anonymous'
  const site =
    typeof window !== 'undefined' ? window.site_name || window.sitename || 'site' : 'site'
  return `nudg:${bucket}:${site}:${user}`
}

/** A restored thread is visible only when this session's inbox includes its WhatsApp account. */
export function threadAccountAllowed(
  account: string | null | undefined,
  accounts: Pick<Account, 'name'>[] | null | undefined,
) {
  if (!account || !accounts?.length) return false
  return accounts.some((row) => row.name === account)
}

/**
 * Older builds stored the last inbox and thread under keys shared by every login
 * on this browser. Delete those rows so the next account cannot read them.
 */
export function purgeSharedDeskCache() {
  if (typeof indexedDB === 'undefined') return
  const request = indexedDB.open('keyval-store')
  request.onupgradeneeded = () => {
    request.transaction?.abort()
    try {
      request.result.close()
    } catch {
      /* the database was not here; leave it uncreated */
    }
  }
  request.onsuccess = () => {
    const db = request.result
    if (!db.objectStoreNames.contains('keyval')) {
      db.close()
      return
    }
    try {
      const tx = db.transaction('keyval', 'readwrite')
      const store = tx.objectStore('keyval')
      for (const key of LEGACY_CACHE_KEYS) store.delete(key)
      tx.oncomplete = () => db.close()
      tx.onerror = () => db.close()
    } catch {
      db.close()
    }
  }
  request.onerror = () => undefined
}
