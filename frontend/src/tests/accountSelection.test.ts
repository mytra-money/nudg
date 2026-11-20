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

  it('keeps All numbers when that was the choice', () => {
    expect(chooseAccount([sales({ assigned: true })], 'all')).toBe('all')
  })

  it('opens on the assigned number when nothing was saved', () => {
    expect(chooseAccount([sales({ assigned: true, is_default: true }), other()], null)).toBe('WhatsApp 0564')
  })

  it('prefers the default among several assigned numbers', () => {
    const accounts = [sales({ assigned: true }), other({ assigned: true, is_default: true })]
    expect(chooseAccount(accounts, null)).toBe('WhatsApp 1000')
  })

  it('opens on All numbers when this user has no assigned number', () => {
    expect(chooseAccount([sales({ is_default: true }), other()], null)).toBe('all')
  })

  it('drops a saved number this user can no longer open', () => {
    expect(chooseAccount([other({ assigned: true })], 'WhatsApp 0564')).toBe('WhatsApp 1000')
  })
})
