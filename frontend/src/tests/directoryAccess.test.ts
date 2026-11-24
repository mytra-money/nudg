import { afterEach, describe, expect, it } from 'vitest'
import { canOpenContacts } from '@/utils/directoryAccess'

describe('contacts sidebar access', () => {
  afterEach(() => {
    delete window.csrf_token
    delete window.directory
  })

  it('follows read permission from the boot payload', () => {
    window.csrf_token = 'token'
    window.directory = {
      profile: { read: false, write: false, create: false, delete: false },
      recipient_list: { read: true, write: false, create: false, delete: false },
    }
    expect(canOpenContacts()).toBe(true)

    window.directory = {
      profile: { read: false, write: false, create: false, delete: false },
      recipient_list: { read: false, write: false, create: false, delete: false },
    }
    expect(canOpenContacts()).toBe(false)
  })

  it('keeps the page available in a local preview', () => {
    delete window.csrf_token
    window.directory = {
      profile: { read: false, write: false, create: false, delete: false },
      recipient_list: { read: false, write: false, create: false, delete: false },
    }
    expect(canOpenContacts()).toBe(true)
  })
})
