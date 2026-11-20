import { describe, expect, it } from 'vitest'
import { applyQuickReplyDraft, filterQuickReplies, slashCommand } from '@/utils/cannedReply'

describe('slashCommand', () => {
  it('detects a trailing slash command', () => {
    expect(slashCommand('/')).toEqual({ open: true, query: '' })
    expect(slashCommand('/gre')).toEqual({ open: true, query: 'gre' })
    expect(slashCommand('Hi /greet')).toEqual({ open: true, query: 'greet' })
  })

  it('only looks at the last line', () => {
    expect(slashCommand('/old\nHello')).toBeNull()
    expect(slashCommand('/old\n/new')).toEqual({ open: true, query: 'new' })
  })

  it('ignores slash mid-token', () => {
    expect(slashCommand('https://x')).toBeNull()
    expect(slashCommand('price is 10/12')).toBeNull()
  })
})

describe('filterQuickReplies', () => {
  const rows = [
    { name: '1', title: 'Greeting', shortcut: 'greet', body: 'Hello there' },
    { name: '2', title: 'Thanks', shortcut: '/thanks', body: 'Thank you' },
  ]

  it('filters by shortcut, title, or body', () => {
    expect(filterQuickReplies(rows, 'gre').map((r) => r.name)).toEqual(['1'])
    expect(filterQuickReplies(rows, 'thank').map((r) => r.name)).toEqual(['2'])
    expect(filterQuickReplies(rows, 'Hello').map((r) => r.name)).toEqual(['1'])
  })

  it('returns all rows for an empty query', () => {
    expect(filterQuickReplies(rows, '')).toHaveLength(2)
  })
})

describe('applyQuickReplyDraft', () => {
  it('replaces the trailing slash token with the reply body', () => {
    expect(applyQuickReplyDraft('/greet', 'Hello!')).toBe('Hello!')
    expect(applyQuickReplyDraft('Hi /gre', 'Hello!')).toBe('Hi Hello!')
    expect(applyQuickReplyDraft('Line1\n/bye', 'See you')).toBe('Line1\nSee you')
  })

  it('clears the slash token when body is empty', () => {
    expect(applyQuickReplyDraft('Hi /x', '')).toBe('Hi ')
  })
})
