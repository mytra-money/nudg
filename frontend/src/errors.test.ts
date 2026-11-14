import { describe, expect, it } from 'vitest'
import { formatErrorMessage } from '@/errors'

describe('formatErrorMessage', () => {
  it('turns a Meta OAuth code 190 into a clean minimal error', () => {
    expect(
      formatErrorMessage(
        '{"error":{"message":"Authentication Error","code":190,"type":"OAuthException","fbtrace_id":"x"}}',
      ),
    ).toBe('Error sending')
  })

  it('turns 24h window closed error into clean message', () => {
    expect(
      formatErrorMessage(
        '{"error":{"message":"Re-engagement message","code":131047}}',
      ),
    ).toBe('Template required')
  })

  it('leaves short plain text alone', () => {
    expect(formatErrorMessage('Template required')).toBe('Template required')
  })
})
