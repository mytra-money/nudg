import { describe, expect, it } from 'vitest'
import { router, shellNav } from '@/router'

describe('desk routes', () => {
  it('exposes the shell routes in order', () => {
    expect(shellNav.map((item) => item.label)).toEqual([
      'Overview',
      'Conversations',
      'Contacts',
      'Marketing',
      'Catalogs',
      'Template Studio',
      'Automation',
      'Analytics',
      'Integrations',
      'Settings',
    ])
    expect(shellNav.map((item) => item.to)).toEqual([
      '/',
      '/conversations',
      '/contacts',
      '/marketing',
      '/catalogs',
      '/template-studio',
      '/automation',
      '/analytics',
      '/integrations',
      '/settings',
    ])
    const registered = router.getRoutes().map((item) => item.path)
    for (const item of shellNav) {
      expect(registered).toContain(item.to)
    }
  })
})
