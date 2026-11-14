import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import TemplateButtonsPreview from '@/components/templates/TemplateButtonsPreview.vue'
import TemplateHeaderPreview from '@/components/templates/TemplateHeaderPreview.vue'
import WhatsAppTemplatePreview from '@/components/templates/WhatsAppTemplatePreview.vue'
import DeskTemplatePreview from '@/components/DeskTemplatePreview.vue'
import type { Template } from '@/types'

const TextInput = {
  name: 'TextInput',
  props: ['modelValue', 'label'],
  emits: ['update:modelValue'],
  template:
    '<label>{{ label }}<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" /></label>',
}

function template(partial: Partial<Template> & Pick<Template, 'name' | 'message'>): Template {
  return {
    template_label: partial.template_label || partial.name,
    template_type: 'Utility',
    language: 'en',
    status: 'Approved',
    buttons: [],
    ...partial,
  }
}

function mountPreview(row: Template, props: Record<string, unknown> = {}) {
  return mount(WhatsAppTemplatePreview, {
    props: { template: row, ...props },
    global: { stubs: { TextInput } },
  })
}

describe('template preview rendering', () => {
  it('renders a text header, formatted body, footer, and sample values', () => {
    const row = template({
      name: 'order',
      header_type: 'Text',
      header_text: 'Order {{1}}',
      message: 'Hello {{name}}.\n\nYour order is ready.',
      footer: 'Thank you for choosing us.',
      template_variables: [
        { variable_name: '1', variable_example: 'ORD-001' },
        { variable_name: 'name', variable_example: 'Nag' },
      ],
    })
    const wrapper = mountPreview(row)
    expect(wrapper.html()).toContain('Order ORD-001')
    expect(wrapper.html()).toContain('Hello Nag')
    expect(wrapper.text()).toContain('Thank you for choosing us.')
    expect(wrapper.find('[aria-label="Template conversation preview"]').exists()).toBe(true)
    expect(wrapper.get('.wa-wallpaper, [role="region"]').classes()).toContain('max-h-80')
  })

  it('renders WhatsApp bold when the body starts with markup', () => {
    const wrapper = mountPreview(
      template({
        name: 'bold',
        message: 'Status *Confirmed* for {{1}}',
        template_variables: [{ variable_name: '1', variable_example: 'ORD-001' }],
      }),
    )
    expect(wrapper.html()).toContain('<b>Confirmed</b>')
    expect(wrapper.html()).toContain('ORD-001')
  })

  it('updates the bubble when a sample value changes and leaves the template untouched', async () => {
    const row = template({
      name: 'order',
      message: 'Hello {{1}}',
      template_variables: [{ variable_name: '1', variable_example: 'Nag' }],
    })
    const wrapper = mountPreview(row)
    await wrapper.get('input').setValue('Meera')
    await nextTick()
    expect(wrapper.text()).toContain('Hello Meera')
    expect(row.template_variables?.[0]?.variable_example).toBe('Nag')
    expect(row.message).toBe('Hello {{1}}')
  })

  it('shows the placeholder again when a sample is cleared', async () => {
    const wrapper = mountPreview(
      template({
        name: 'order',
        message: 'Hello {{1}}',
        template_variables: [{ variable_name: '1', variable_example: 'Nag' }],
      }),
    )
    await wrapper.get('input').setValue('')
    await nextTick()
    expect(wrapper.text()).toContain('Hello {{1}}')
  })

  it('renders image, video, document, gif, and unsupported headers', () => {
    const image = mount(TemplateHeaderPreview, {
      props: { headerType: 'Image', mediaUrl: 'data:image/svg+xml,%3Csvg%3E%3C/svg%3E' },
    })
    expect(image.get('img').attributes('src')).toContain('data:image/svg+xml')

    const hidden = mount(TemplateHeaderPreview, {
      props: { headerType: 'Image', mediaUrl: '/private/files/secret.jpg' },
    })
    expect(hidden.find('img').exists()).toBe(false)
    expect(hidden.text()).toContain('No public example image')

    const video = mount(TemplateHeaderPreview, { props: { headerType: 'Video', mediaUrl: '/files/clip.mp4' } })
    expect(video.text()).toContain('Video header')
    expect(video.text()).toContain('clip.mp4')
    expect(video.find('video').exists()).toBe(false)

    const document = mount(TemplateHeaderPreview, {
      props: { headerType: 'Document', mediaUrl: '/files/invoice.pdf', mimeType: 'application/pdf' },
    })
    expect(document.text()).toContain('invoice.pdf')
    expect(document.text()).toContain('PDF')

    const gif = mount(TemplateHeaderPreview, { props: { headerType: 'GIF' } })
    expect(gif.text()).toContain('GIF header')

    const unknown = mount(TemplateHeaderPreview, { props: { headerType: 'Location' } })
    expect(unknown.text()).toContain('Unsupported header: Location')
  })

  it('replaces an image with a placeholder when the file cannot be loaded', async () => {
    const wrapper = mount(TemplateHeaderPreview, {
      props: { headerType: 'Image', mediaUrl: 'https://cdn.example.com/missing.jpg' },
    })
    await wrapper.get('img').trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.text()).toContain('No public example image')
  })

  it('renders known buttons as text and refuses links', () => {
    const wrapper = mount(TemplateButtonsPreview, {
      props: {
        samples: { code: 'SAVE10' },
        buttons: [
          { button_type: 'Quick Reply', button_text: 'Track Order' },
          { button_type: 'URL', button_text: 'Open', url: 'https://example.com/{{code}}' },
          { button_type: 'Phone Number', button_text: 'Call', phone_number: '+91 98000 00000' },
          { button_type: 'Copy Code', button_text: 'Copy offer' },
          { button_type: 'Voice Call', button_text: 'Voice' },
          { button_type: 'OTP', button_text: 'One time' },
        ],
      },
    })
    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.html()).not.toContain('href=')
    expect(wrapper.html()).not.toContain('tel:')
    expect(wrapper.text()).toContain('Track Order')
    expect(wrapper.text()).toContain('https://example.com/SAVE10')
    expect(wrapper.text()).toContain('+91 98000 00000')
    expect(wrapper.text()).toContain('Copy offer')
    expect(wrapper.text()).toContain('Voice call')
    expect(wrapper.text()).toContain('Unsupported button: OTP')
  })

  it('keeps the raw tab on the stored template text', () => {
    const row = template({
      name: 'order',
      header_type: 'Image',
      header_media: '/files/lot.jpg',
      message: 'Hello {{1}}',
      template_variables: [{ variable_name: '1', variable_example: 'Nag' }],
    })
    const wrapper = mount(DeskTemplatePreview, {
      props: { template: row, mode: 'raw' },
      global: { stubs: { TextInput } },
    })
    expect(wrapper.text()).toContain('Raw template')
    expect(wrapper.text()).toContain('Hello {{1}}')
    expect(wrapper.text()).toContain('/files/lot.jpg')
    expect(wrapper.text()).not.toContain('Hello Nag')
  })

  it('renders approved templates in the shape stored by frappe/whatsapp 1.2.0', () => {
    const order = mountPreview(
      template({
        name: '0mo9se1mqd',
        template_label: 'jaspers_market_order_confirmation_v1',
        template_type: 'Utility',
        language: 'en_US',
        header_type: 'Text',
        header_text: 'Order confirmed',
        message:
          "Hi {{1}},\n\nThank you for your purchase! Your order number is {{2}}.\n\nWe'll start getting your farm fresh groceries ready to ship.\n\nEstimated delivery:  {{3}}.",
        footer: 'developers.facebook.com',
        variable_format: 'Positional',
        template_variables: [
          { variable_name: '1', variable_example: '1' },
          { variable_name: '2', variable_example: '2' },
          { variable_name: '3', variable_example: '3' },
        ],
        buttons: [
          {
            button_type: 'URL',
            button_text: 'Visit order details',
            url: 'https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates/utility-templates',
          },
        ],
      }),
    )
    expect(order.text()).toContain('Order confirmed')
    expect(order.text()).toContain('Hi 1,')
    expect(order.text()).toContain('Your order number is 2.')
    expect(order.text()).toContain('Estimated delivery:  3.')
    expect(order.text()).toContain('developers.facebook.com')
    expect(order.text()).toContain('Visit order details')
    expect(order.find('a').exists()).toBe(false)

    const image = mount(TemplateHeaderPreview, { props: { headerType: 'Image', mediaUrl: '' } })
    expect(image.find('img').exists()).toBe(false)
    expect(image.text()).toContain('Image header')
  })

  it('hides the sample editor when editing is off', () => {
    const wrapper = mountPreview(
      template({
        name: 'order',
        message: 'Hello {{1}}',
        template_variables: [{ variable_name: '1', variable_example: 'Nag' }],
      }),
      { editable: false },
    )
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.text()).toContain('Hello Nag')
  })
})
