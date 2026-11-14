import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { call } from 'frappe-ui'
import LogsView from '@/components/LogsView.vue'

vi.mock('frappe-ui', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    call: vi.fn(),
  }
})

describe('LogsView', () => {
  beforeEach(() => {
    window.csrf_token = undefined
    vi.mocked(call).mockReset()
  })

  it('renders Audit Logs header, KPI cards, and log rows', async () => {
    const wrapper = mount(LogsView, {
      global: {
        stubs: {
          RouterLink: {
            template: '<a><slot /></a>',
          },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Message & Webhook Audit Logs')
    expect(wrapper.text()).toContain('Total Audit Events')
    expect(wrapper.text()).toContain('Meta API Errors')
    expect(wrapper.text()).toContain('Sundarban Sales')
    expect(wrapper.text()).toContain('Meta rejected the text')
    expect(wrapper.text()).toContain('Inbound message stored for Meera Iyer')
  })

  it('filters logs by level when Level button is clicked', async () => {
    const wrapper = mount(LogsView, {
      global: {
        stubs: {
          RouterLink: {
            template: '<a><slot /></a>',
          },
        },
      },
    })
    await flushPromises()

    const errorBtn = wrapper.findAll('button').find((b) => b.text() === 'Error')
    expect(errorBtn).toBeDefined()

    await errorBtn!.trigger('click')
    expect(wrapper.text()).toContain('Meta rejected the text')
    expect(wrapper.text()).not.toContain('Inbound message stored for Meera Iyer')
  })

  it('searches logs by text query', async () => {
    const wrapper = mount(LogsView, {
      global: {
        stubs: {
          RouterLink: {
            template: '<a><slot /></a>',
          },
        },
      },
    })
    await flushPromises()

    const searchInput = wrapper.find('input[placeholder="Search message, docname, event..."]')
    expect(searchInput.exists()).toBe(true)

    await searchInput.setValue('Meera')
    expect(wrapper.text()).toContain('Inbound message stored for Meera Iyer')
    expect(wrapper.text()).not.toContain('Meta rejected the text')
  })

  it('expands raw payload when View Raw Payload is clicked', async () => {
    const wrapper = mount(LogsView, {
      global: {
        stubs: {
          RouterLink: {
            template: '<a><slot /></a>',
          },
        },
      },
    })
    await flushPromises()

    const payloadBtn = wrapper.findAll('button').find((b) => b.text().includes('View Raw Payload'))
    expect(payloadBtn).toBeDefined()

    await payloadBtn!.trigger('click')
    expect(wrapper.text()).toContain('Hide Payloads')
    expect(wrapper.text()).toContain('Copy JSON')
  })
})
