import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { call } from 'frappe-ui'
import CatalogsView from '@/pages/Catalogs.vue'

vi.mock('frappe-ui', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    call: vi.fn(),
  }
})

describe('CatalogsView', () => {
  beforeEach(() => {
    window.csrf_token = undefined
    vi.mocked(call).mockReset()
  })

  it('renders Commerce Catalogs header, collections, and products', async () => {
    const wrapper = mount(CatalogsView, {
      global: {
        stubs: {
          RouterLink: {
            template: '<a><slot /></a>',
          },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('WhatsApp Product Catalogs')
    expect(wrapper.text()).toContain('Sundarban Signature Spices')
    expect(wrapper.text()).toContain('Festive Hampers & Spice Trunks')
    expect(wrapper.text()).toContain('Royal Green Cardamom')
    expect(wrapper.text()).toContain('Tellicherry Black Pepper')
    expect(wrapper.text()).toContain('Stored on this site')
    expect(wrapper.text()).toContain('Meta Commerce Catalog sync is not enabled in this build.')
    expect(wrapper.text()).not.toContain('Meta Commerce Manager Active')
  })

  it('filters product items by search query', async () => {
    const wrapper = mount(CatalogsView, {
      global: {
        stubs: {
          RouterLink: {
            template: '<a><slot /></a>',
          },
        },
      },
    })
    await flushPromises()

    const itemSearch = wrapper.find('input[placeholder="Search products or SKU..."]')
    expect(itemSearch.exists()).toBe(true)

    await itemSearch.setValue('Saffron')
    expect(wrapper.text()).toContain('Organic Kashmiri Mongra Saffron')
    expect(wrapper.text()).not.toContain('Tellicherry Black Pepper')
  })

  it('opens Single-Product Message modal when Send to Customer is clicked', async () => {
    const wrapper = mount(CatalogsView, {
      global: {
        stubs: {
          RouterLink: {
            template: '<a><slot /></a>',
          },
        },
      },
    })
    await flushPromises()

    const sendBtn = wrapper.findAll('button').find((btn) => btn.text().includes('Send to Customer'))
    expect(sendBtn).toBeDefined()

    await sendBtn!.trigger('click')
    await flushPromises()
    const content = document.body.textContent || wrapper.text()
    expect(content).toContain('Send Single-Product Message (SPM)')
    expect(content).toContain('Customer Chat Preview')
    expect(content).toContain('View Product')
  })
})
