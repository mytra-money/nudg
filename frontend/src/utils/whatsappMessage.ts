import type {
  WhatsAppDirection,
  WhatsAppMessage,
  WhatsAppReaction,
  WhatsAppStatus,
  WhatsAppTemplateButton,
} from '@whatsapp/ui/components/Messages'
import { formatErrorMessage } from '@/utils/errors'
import type { ChatMessage, TemplateButton } from '@/types'

const STATUSES = new Set<WhatsAppStatus>(['Pending', 'Sent', 'Delivered', 'Read', 'Failed'])
const BUTTON_TYPES = new Set<WhatsAppTemplateButton['button_type']>([
  'Quick Reply',
  'URL',
  'Copy Code',
  'Phone Number',
  'Voice Call',
])

function directionOf(value?: string | null): WhatsAppDirection | undefined {
  if (value === 'Incoming' || value === 'Outgoing') return value
  return undefined
}

function statusOf(value?: string | null): WhatsAppStatus | undefined {
  if (!value) return undefined
  const titled = (value.charAt(0).toUpperCase() + value.slice(1).toLowerCase()) as WhatsAppStatus
  return STATUSES.has(titled) ? titled : undefined
}

export function toTemplateButtons(rows?: TemplateButton[] | null): WhatsAppTemplateButton[] | undefined {
  if (!rows?.length) return undefined
  const buttons: WhatsAppTemplateButton[] = []
  for (const row of rows) {
    if (!BUTTON_TYPES.has(row.button_type as WhatsAppTemplateButton['button_type'])) continue
    buttons.push({
      button_type: row.button_type as WhatsAppTemplateButton['button_type'],
      button_text: row.button_text,
      url: row.url,
      phone_number: row.phone_number,
    })
  }
  return buttons.length ? buttons : undefined
}

function reactionsOf(rows?: ChatMessage['reactions']): WhatsAppReaction[] | undefined {
  if (!rows?.length) return undefined
  const reactions: WhatsAppReaction[] = []
  for (const row of rows) {
    const direction = directionOf(row.direction)
    if (!direction || !row.emoji) continue
    reactions.push({ emoji: row.emoji, direction })
  }
  return reactions.length ? reactions : undefined
}

/**
 * Map a desk thread onto the message shape `MessageList` renders.
 * Reply quotes key off `context_message_id`, which sample sends store as `reply_to`.
 */
export function toWhatsAppMessages(rows: ChatMessage[]): WhatsAppMessage[] {
  const byName = new Map<string, ChatMessage>()
  const byId = new Map<string, ChatMessage>()
  for (const row of rows) {
    byName.set(row.name, row)
    if (row.message_id) byId.set(row.message_id, row)
  }

  return rows.map((row) => {
    const target = row.reply_to
      ? byName.get(row.reply_to)
      : row.context_message_id
        ? byId.get(row.context_message_id) || byName.get(row.context_message_id)
        : undefined
    const context = row.context_message_id || (row.reply_to ? target?.message_id || row.reply_to : undefined)
    return {
      name: row.name,
      direction: row.direction,
      creation: row.creation,
      message: row.message || (row.is_template ? row.template : undefined),
      status: statusOf(row.status),
      to: row.to,
      mime_type: row.mime_type,
      media_url: row.media_url,
      is_template: row.is_template,
      whatsapp_template: row.whatsapp_template,
      message_id: row.message_id,
      context_message_id: context,
      reference_doctype: row.reference_doctype,
      reference_docname: row.reference_docname,
      reaction: row.reaction || undefined,
      error_message: formatErrorMessage(row.error_message),
      reactions: reactionsOf(row.reactions),
      file_name: row.file_name,
      reply_message: row.reply_message || target?.message || target?.template,
      reply_to: row.reply_to || target?.name,
      reply_to_direction: directionOf(row.reply_to_direction) || target?.direction,
      template: row.template,
      header: row.header,
      footer: row.footer,
      buttons: toTemplateButtons(row.buttons),
      template_name: row.template_label,
    }
  })
}
