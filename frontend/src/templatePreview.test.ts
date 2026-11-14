import { describe, expect, it } from 'vitest'
import {
  exampleMap,
  fallbackSample,
  fillVariables,
  headerKind,
  mediaFileName,
  mediaTypeLabel,
  previewVariableNames,
  publicMediaUrl,
  resolveSampleValues,
  variableNames,
} from '@/templatePreview'

describe('template preview variables', () => {
  it('replaces variables with stored examples', () => {
    const examples = exampleMap([
      { variable_name: '1', variable_example: 'Nagaraju' },
      { variable_name: '2', variable_example: '20%' },
    ])
    expect(fillVariables('Hello {{1}}, get up to {{2}} off', examples)).toBe(
      'Hello Nagaraju, get up to 20% off',
    )
  })

  it('replaces a single variable, repeated variables, and spaced braces', () => {
    const examples = new Map([['1', 'Nag']])
    expect(fillVariables('Hi {{1}}. Again, {{ 1 }}.', examples)).toBe('Hi Nag. Again, Nag.')
  })

  it('keeps the placeholder when a value is missing or empty', () => {
    const examples = new Map<string, string>([['2', '']])
    expect(fillVariables('Hello {{1}}, order {{2}}', examples)).toBe('Hello {{1}}, order {{2}}')
  })

  it('reads named and positional placeholders the way the WhatsApp app does', () => {
    expect(variableNames('Hello {{name}}, order {{ order_id }}.', 'Due {{1}}')).toEqual([
      'name',
      'order_id',
      '1',
    ])
  })

  it('collects header, body, and URL variables without duplicating stored rows', () => {
    expect(
      previewVariableNames({
        header_text: 'Order {{1}}',
        message: 'Hello {{name}}',
        buttons: [{ url: 'https://example.com/{{name}}' }],
        template_variables: [
          { variable_name: 'name', variable_example: 'Nag' },
          { variable_name: 'city' },
        ],
      }),
    ).toEqual(['1', 'name', 'city'])
  })

  it('prefers stored examples and fills the rest with samples', () => {
    const values = resolveSampleValues({
      message: 'Hello {{1}}, order {{2}}, total {{3}}, on {{4}}, plus {{5}}. City {{city}}.',
      template_variables: [{ variable_name: '1', variable_example: 'Meera' }],
    })
    expect(values).toEqual({
      '1': 'Meera',
      '2': 'ORD-001',
      '3': '₹2,499',
      '4': '10 November 2026',
      '5': 'Sample 5',
      city: 'Sample',
    })
  })

  it('uses a named sample when the template has no example', () => {
    expect(fallbackSample('order_id')).toBe('ORD-001')
    expect(fallbackSample('customer_name')).toBe('Nag')
    expect(resolveSampleValues({ message: 'Hello {{customer_name}}' }).customer_name).toBe('Nag')
  })

  it('does not treat a blank stored example as a sample override', () => {
    expect(
      resolveSampleValues({
        message: 'Hello {{1}}',
        template_variables: [{ variable_name: '1', variable_example: '   ' }],
      })['1'],
    ).toBe('Nag')
  })

  it('fills from a plain object so an edited sample updates immediately', () => {
    const samples = { '1': 'Nag' }
    expect(fillVariables('Hello {{1}}', samples)).toBe('Hello Nag')
    samples['1'] = ''
    expect(fillVariables('Hello {{1}}', samples)).toBe('Hello {{1}}')
  })
})

describe('template preview media', () => {
  it('allows public file URLs and image data URLs', () => {
    expect(publicMediaUrl('/files/lot.jpg')).toBe('/files/lot.jpg')
    expect(publicMediaUrl('https://cdn.example.com/lot.jpg')).toBe('https://cdn.example.com/lot.jpg')
    expect(publicMediaUrl('data:image/svg+xml,%3Csvg%3E')).toMatch(/^data:image\/svg\+xml/)
  })

  it('does not request private or non-http media', () => {
    expect(publicMediaUrl('/private/files/secret.pdf')).toBeNull()
    expect(publicMediaUrl('https://site.example/private/files/secret.pdf')).toBeNull()
    expect(publicMediaUrl('javascript:alert(1)')).toBeNull()
    expect(publicMediaUrl('../files/secret.pdf')).toBeNull()
  })

  it('maps the header types stored on WA Template', () => {
    expect(headerKind(undefined)).toBe('text')
    expect(headerKind('Text')).toBe('text')
    expect(headerKind('Image')).toBe('image')
    expect(headerKind('Video')).toBe('video')
    expect(headerKind('Document')).toBe('document')
    expect(headerKind('GIF')).toBe('gif')
    expect(headerKind('Location')).toBe('unsupported')
  })

  it('reads a document name and type without opening the file', () => {
    expect(mediaFileName('/private/files/Invoice%201.pdf')).toBe('Invoice 1.pdf')
    expect(mediaTypeLabel('application/pdf', 'Invoice 1.pdf')).toBe('PDF')
    expect(mediaTypeLabel(undefined, 'notes.docx')).toBe('DOCX')
    expect(mediaFileName(undefined)).toBe('Document')
  })
})
