import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { call } from 'frappe-ui'
import SettingsView from '@/pages/Settings.vue'

vi.mock('frappe-ui', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    call: vi.fn(),
  }
})

describe('SettingsView', () => {
  beforeEach(() => {
    window.csrf_token = undefined
    vi.mocked(call).mockReset()
  })

  it('renders Settings tabs, KPI cards, and quick replies', async () => {
    const wrapper = mount(SettingsView)
    await flushPromises()

    // Page title lives in AppShell; the view owns tabs + reply content.
    expect(wrapper.text()).toContain('Quick Replies')
    expect(wrapper.text()).toContain('Routing & Assignment')
    expect(wrapper.text()).toContain('WABA Profile')
    expect(wrapper.text()).toContain('Welcome & Inquiry Greeting')
    expect(wrapper.text()).toContain('/greet')
  })

  it('filters quick replies by search query', async () => {
    const wrapper = mount(SettingsView)
    await flushPromises()

    const searchInput = wrapper.find('input[placeholder="Search title, /shortcut, body..."]')
    expect(searchInput.exists()).toBe(true)

    await searchInput.setValue('lots')
    expect(wrapper.text()).toContain('Weekly Lots & Price Sheet')
    expect(wrapper.text()).not.toContain('Dispatch & Courier Tracking')
  })

  it('switches to Routing & Assignment tab and displays configuration', async () => {
    const wrapper = mount(SettingsView)
    await flushPromises()

    const routingTabBtn = wrapper.findAll('button').find((b) => b.text().includes('Routing & Assignment'))
    expect(routingTabBtn).toBeDefined()

    await routingTabBtn!.trigger('click')
    expect(wrapper.text()).toContain('Frappe Assignment Rules')
  })

  it('switches to WABA Profile tab and displays Meta verified metadata', async () => {
    const wrapper = mount(SettingsView)
    await flushPromises()

    const profileTabBtn = wrapper.findAll('button').find((b) => b.text().includes('WABA Profile'))
    expect(profileTabBtn).toBeDefined()

    await profileTabBtn!.trigger('click')
    expect(wrapper.text()).toContain('Sundarban Spices & Agri Corp')
    expect(wrapper.text()).toContain('Meta Verified Business')
    expect(wrapper.text()).toContain('Tier 1 · 10,000 unique recipients / 24h')
  })
})
