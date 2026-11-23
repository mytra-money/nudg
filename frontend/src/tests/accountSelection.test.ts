import { describe, expect, it } from 'vitest'
import { chooseAccount } from '@/utils/accountSelection'
import type { Account } from '@/types'

const sales = (extra: Partial<Account> = {}): Account => ({
  name: 'WhatsApp 0564',
  account_name: 'WhatsApp 0564',
  status: 'Active',
  ...extra,
})

const other = (extra: Partial<Account> = {}): Account => ({
  name: 'WhatsApp 1000',
  account_name: 'WhatsApp 1000',
  status: 'Active',
  ...extra,
})

describe('number dropdown', () => {
  it('keeps the number chosen before a refresh', () => {
    expect(chooseAccount([sales(), other()], 'WhatsApp 0564')).toBe('WhatsApp 0564')
  })

  it('never returns all, even when "all" was saved earlier', () => {
    expect(chooseAccount([sales({ assigned: true })], 'all')).toBe('WhatsApp 0564')
  })

  it('returns an empty string when there are no numbers', () => {
    expect(chooseAccount([], null)).toBe('')
  })

  it('opens on the assigned number when nothing was saved', () => {
    expect(chooseAccount([sales({ assigned: true, is_default: true }), other()], null)).toBe('WhatsApp 0564')
  })

  it('prefers the default among several assigned numbers', () => {
    const accounts = [sales({ assigned: true }), other({ assigned: true, is_default: true })]
    expect(chooseAccount(accounts, null)).toBe('WhatsApp 1000')
  })

  it('opens on the default visible number when this user has no assigned number', () => {
    expect(chooseAccount([other(), sales({ is_default: true })], null)).toBe('WhatsApp 0564')
  })

  it('opens on the first visible number when none is assigned or default', () => {
    expect(chooseAccount([other(), sales()], null)).toBe('WhatsApp 1000')
  })

  it('drops a saved number this user can no longer open', () => {
    expect(chooseAccount([other({ assigned: true })], 'WhatsApp 0564')).toBe('WhatsApp 1000')
  })
})
