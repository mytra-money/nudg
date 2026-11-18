import { describe, expect, it } from 'vitest'
import { computeIsSiteAdmin } from '@/stores/session'

describe('site admin', () => {
  it('treats Administrator and System Manager as site admins', () => {
    window.user = 'agent@example.com'
    window.roles = ['WhatsApp Manager']
    window.is_system_manager = false
    expect(computeIsSiteAdmin()).toBe(false)

    window.is_system_manager = true
    expect(computeIsSiteAdmin()).toBe(true)
  })

  it('falls back to roles when the boot flag is missing', () => {
    delete window.is_system_manager
    window.user = 'owner@example.com'
    window.roles = ['System Manager']
    expect(computeIsSiteAdmin()).toBe(true)

    window.roles = ['WhatsApp User']
    window.user = 'Administrator'
    expect(computeIsSiteAdmin()).toBe(true)

    window.user = 'agent@example.com'
    expect(computeIsSiteAdmin()).toBe(false)
  })
})
