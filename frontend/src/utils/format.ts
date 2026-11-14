import type { ChatMessage, WindowState } from '@/types'
import { formatErrorMessage } from '@/utils/errors'

const WINDOW_MS = 24 * 60 * 60 * 1000

export function contentKind(mime?: string) {
  if (!mime) return 'text'
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('audio/')) return 'audio'
  if (mime.startsWith('video/')) return 'video'
  return 'document'
}

export function serviceWindow(messages: ChatMessage[], now = Date.now()): WindowState {
  const incoming = messages.filter((message) => message.direction === 'Incoming' && !message.reaction)
  const last = incoming[incoming.length - 1]
  if (!last) return { status: 'unopened', expires_at: null, last_incoming_at: null }
  const opened = new Date(last.creation).getTime()
  const expires = opened + WINDOW_MS
  return {
    status: expires > now ? 'open' : 'closed',
    expires_at: new Date(expires).toISOString(),
    last_incoming_at: new Date(opened).toISOString(),
  }
}

export function previewText(message?: ChatMessage | null) {
  if (!message) return 'No messages yet'
  if (message.is_template) return message.template || message.template_label || message.message || 'Template'
  if (message.message) return message.message
  const kind = contentKind(message.mime_type)
  if (kind === 'image') return 'Photo'
  if (kind === 'audio') return 'Voice note'
  if (kind === 'video') return 'Video'
  if (kind === 'document') return message.file_name || 'Document'
  return 'Message'
}

export function initials(name?: string) {
  const source = (name || '?').trim()
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0]![0]! + parts[1]![0]!).toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

export function formatTime(value?: string | null) {
  if (!value) return ''
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

export function formatDay(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  const today = new Date()
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (sameDay(date, today)) return 'Today'
  if (sameDay(date, yesterday)) return 'Yesterday'
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

export function formatRemaining(expiresAt?: string | null, now = Date.now()) {
  if (!expiresAt) return ''
  const ms = new Date(expiresAt).getTime() - now
  if (ms <= 0) return 'closed'
  const hours = Math.floor(ms / 3_600_000)
  const minutes = Math.floor((ms % 3_600_000) / 60_000)
  if (hours >= 1) return `${hours}h ${minutes}m left`
  return `${Math.max(minutes, 1)}m left`
}

export function deskRoute(doctype: string, name: string) {
  const slug = doctype.toLowerCase().replace(/ /g, '-')
  return `/app/${slug}/${encodeURIComponent(name)}`
}

/** In-app screen for a DocType, when Nudg already has one. */
export function whatsappScreen(doctype: string): { path: string; manager?: boolean } | null {
  const key = doctype.trim().toLowerCase()
  const screens: Record<string, { path: string; manager?: boolean }> = {
    'wa template': { path: '/template-studio' },
    'wa account': { path: '/integrations', manager: true },
    'whatsapp catalog': { path: '/integrations/catalogs', manager: true },
    'whatsapp catalog item': { path: '/integrations/catalogs', manager: true },
    'utm campaign': { path: '/marketing', manager: true },
    'whatsapp quick reply': { path: '/settings' },
    'whatsapp automation rule': { path: '/automation', manager: true },
    'whatsapp automation run': { path: '/automation', manager: true },
    'wa log': { path: '/integrations/logs', manager: true },
    'nudg conversation': { path: '/conversations' },
    'wa profile': { path: '/conversations' },
    'wa message': { path: '/conversations' },
  }
  return screens[key] || null
}

export function errorText(error: unknown): string {
  if (error && typeof error === 'object' && 'messages' in error) {
    const messages = (error as { messages?: string[] }).messages
    if (messages?.length) return formatErrorMessage(messages.join(' ')) || 'Error sending'
  }
  if (error instanceof Error && error.message) {
    return formatErrorMessage(error.message) || 'Error sending'
  }
  if (typeof error === 'string') {
    return formatErrorMessage(error) || 'Error sending'
  }
  return 'Error sending'
}

/** Full server message for a failed action. Does not shorten it to "Error sending". */
export function rawErrorText(error: unknown): string {
  const parts: string[] = []
  if (error && typeof error === 'object' && 'messages' in error) {
    const messages = (error as { messages?: unknown }).messages
    if (Array.isArray(messages)) {
      for (const message of messages) {
        if (message) parts.push(String(message))
      }
    }
  }
  if (!parts.length && error instanceof Error && error.message) parts.push(error.message)
  if (!parts.length && typeof error === 'string') parts.push(error)
  const text = parts
    .join('\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return text || 'Catalog product could not be sent.'
}
