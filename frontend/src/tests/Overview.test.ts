import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { call } from 'frappe-ui'
import OverviewView from '@/pages/Overview.vue'

vi.mock('frappe-ui', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    call: vi.fn(),
  }
})

describe('OverviewView status', () => {
  beforeEach(() => {
    window.csrf_token = 'token'
    window.whatsapp_installed = undefined
    window.integration = undefined
    vi.mocked(call).mockReset()
  })

  it('renders an error when the status call fails', async () => {
    vi.mocked(call).mockRejectedValue(new Error('Failed to get method'))
    const wrapper = mount(OverviewView)
    await flushPromises()

    expect(call).toHaveBeenCalledWith('nudg.api.get_integration_status')
    expect(wrapper.find('[data-state="error"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Could not load integration status')
    expect(wrapper.text()).toContain('Failed to get method')
    expect(wrapper.text()).not.toContain('DocTypes')
    // Page title lives in AppShell; the view still shows the overview blurb.
    expect(wrapper.text()).toContain('conversation SLAs')
  })
})
