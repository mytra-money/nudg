export interface DocAccess {
  read: boolean
  write: boolean
  create: boolean
  delete: boolean
}

export interface DirectoryAccess {
  profile: DocAccess
  recipient_list: DocAccess
}

function flag(value: unknown): boolean {
  return value === true || value === 1 || value === '1'
}

function normalize(value: Partial<DocAccess> | undefined): DocAccess {
  return {
    read: flag(value?.read),
    write: flag(value?.write),
    create: flag(value?.create),
    delete: flag(value?.delete),
  }
}

/** Permissions shipped with the page boot. Null when the boot has no directory block. */
export function bootDirectoryAccess(): DirectoryAccess | null {
  if (typeof window === 'undefined' || !window.directory) return null
  return {
    profile: normalize(window.directory.profile),
    recipient_list: normalize(window.directory.recipient_list),
  }
}

/**
 * Show the Contacts sidebar when this user can read contacts or recipient lists.
 * A local preview with no session still shows the page.
 */
export function canOpenContacts(): boolean {
  if (typeof window === 'undefined') return true
  if (!window.csrf_token) return true
  const access = bootDirectoryAccess()
  if (!access) return true
  return access.profile.read || access.recipient_list.read
}
