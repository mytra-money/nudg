import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { call } from 'frappe-ui'
import AccountsView from '@/components/AccountsView.vue'

vi.mock('frappe-ui', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    call: vi.fn(),
  }
})

describe('AccountsView', () => {
  beforeEach(() => {
    window.csrf_token = undefined
    vi.mocked(call).mockReset()
  })

  it('shows connected numbers without operator diagnostics', async () => {
    const wrapper = mount(AccountsView)
    await flushPromises()

    expect(wrapper.text()).toContain('WhatsApp numbers')
    expect(wrapper.text()).toContain('Sundarban Sales')
    expect(wrapper.text()).toContain('Sundarban Dispatch')
    expect(wrapper.text()).toContain('Default number')
    expect(wrapper.text()).not.toContain('Dual-Mode Ready')
    expect(wrapper.text()).not.toContain('Webhook Endpoints')
    expect(wrapper.text()).not.toContain('Ping Gateway')
  })

  it('filters accounts by search query', async () => {
    const wrapper = mount(AccountsView)
    await flushPromises()

    const input = wrapper.find('input[placeholder="Search numbers"]')
    expect(input.exists()).toBe(true)

    await input.setValue('Sales')
    expect(wrapper.text()).toContain('Sundarban Sales')
    expect(wrapper.text()).not.toContain('Sundarban Dispatch')
  })

  it('opens credentials in a separate dialog', async () => {
    const wrapper = mount(AccountsView, { attachTo: document.body })
    await flushPromises()

    const connect = wrapper.findAll('button').find((btn) => btn.text().includes('Connect number'))
    expect(connect).toBeDefined()
    await connect!.trigger('click')
    await flushPromises()

    const content = document.body.textContent || ''
    expect(content).toContain('Login with Facebook')
    expect(content).toContain('I already have credentials')
    expect(content).not.toContain('Phone number ID')

    const credentials = [...document.querySelectorAll('button')].find((btn) =>
      btn.textContent?.includes('I already have credentials'),
    )
    expect(credentials).toBeTruthy()
    credentials!.click()
    await flushPromises()

    expect(document.body.textContent || '').toContain('Phone number ID')
    wrapper.unmount()
  })
})
