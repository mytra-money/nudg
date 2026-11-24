import { describe, expect, it } from 'vitest'
import { displayTitle, isDocumentId } from '@/utils/titles'

describe('display titles', () => {
  it('hides series ids and hash ids', () => {
    expect(isDocumentId('WA-CAMP-2026-00004')).toBe(true)
    expect(isDocumentId('BULK-WA-2026-00009')).toBe(true)
    expect(isDocumentId('cfge1k02e5')).toBe(true)
    expect(isDocumentId('Festive allocation')).toBe(false)
    expect(isDocumentId('WhatsApp 6909')).toBe(false)
  })

  it('uses the first real title', () => {
    expect(displayTitle('cfge1k02e5', 'send_quotation1')).toBe('send_quotation1')
    expect(displayTitle('', 'WA-CAMP-2026-00004', 'Test')).toBe('Test')
    expect(displayTitle('fciao1gr53')).toBe('')
  })
})