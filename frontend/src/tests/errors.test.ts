import { describe, expect, it } from 'vitest'
import { formatErrorMessage, userFacingError } from '@/utils/errors'

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

describe('userFacingError', () => {
  it('hides a raw Graph API dump', () => {
    expect(
      userFacingError(
        "Unsupported post request. Object with ID '2436551013419081' does not exist. https://developers.facebook.com/docs/graph-api",
        'WhatsApp could not finish setup. Try connecting again.',
      ),
    ).toBe('WhatsApp could not finish setup. Try connecting again.')
  })

  it('hides an OAuth JSON dump inside a log line', () => {
    expect(
      userFacingError(
        'Failed to send message: {"error":{"message":"Invalid OAuth access token","code":190}}',
        'Something went wrong.',
      ),
    ).toBe('Something went wrong.')
  })

  it('keeps a short Frappe message', () => {
    expect(userFacingError('Save the Meta App ID, configuration ID, and app secret before connecting.')).toBe(
      'Save the Meta App ID, configuration ID, and app secret before connecting.',
    )
  })
})
