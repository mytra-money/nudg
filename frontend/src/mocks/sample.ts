import { serviceWindow } from '@/utils/format'
import type { Account, ChatMessage, Conversation, Inbox, LogRow, Profile, Template, Thread } from '@/types'

function ago(minutes: number) {
  return new Date(Date.now() - minutes * 60_000).toISOString()
}

const SALES = 'Sundarban Sales'
const DISPATCH = 'Sundarban Dispatch'

const photo = (title: string, note: string) => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="720" height="440"><rect width="720" height="440" fill="#efe6d4"/><rect x="36" y="36" width="648" height="368" rx="28" fill="#f7f1e4" stroke="#d9cbb0"/><circle cx="250" cy="210" r="78" fill="#2f6a45"/><text x="390" y="200" font-family="Georgia, serif" font-size="32" fill="#2a241c">${title}</text><text x="390" y="236" font-family="Georgia, serif" font-size="16" fill="#6d6256">${note}</text></svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

export const accounts: Account[] = [
  { name: SALES, account_name: SALES, status: 'Active', auto_read_receipts: true, is_default: true },
  { name: DISPATCH, account_name: DISPATCH, status: 'Active', auto_read_receipts: false, is_default: false },
]

export const templates: Template[] = [
  {
    name: 'tpl-dispatch',
    template_label: 'Dispatch notice',
    template_name: 'dispatch_notice',
    template_type: 'Utility',
    language: 'en',
    status: 'Approved',
    header_type: 'Text',
    message: 'Your order {{1}} has left the warehouse and is due {{2}}.',
    footer: 'Sundarban Spices',
    reference_doctype: 'Sales Order',
    whatsapp_account: DISPATCH,
    variable_format: 'Positional',
    template_variables: [
      { variable_name: '1', variable_example: 'MAT-DN-0194' },
      { variable_name: '2', variable_example: 'tomorrow morning' },
    ],
    buttons: [{ button_type: 'URL', button_text: 'Track', url: 'https://example.com/track' }],
  },
  {
    name: 'tpl-price',
    template_label: 'Price list',
    template_name: 'price_list',
    template_type: 'Marketing',
    language: 'en',
    status: 'Approved',
    header_type: 'Text',
    header_text: 'This week’s lots',
    message: 'Cardamom and black pepper are ready to book. Reply if you want the sheet.',
    whatsapp_account: SALES,
    buttons: [{ button_type: 'Quick Reply', button_text: 'Send the sheet' }],
  },
  {
    name: 'tpl-festive',
    template_label: 'Festive allocation',
    template_name: 'festive_allocation',
    template_type: 'Marketing',
    language: 'en',
    status: 'Pending',
    header_type: 'Video',
    message: 'We are holding a festive allocation for you.',
    whatsapp_account: SALES,
    buttons: [{ button_type: 'Phone Number', button_text: 'Call the desk', phone_number: '+91 33 4000 1100' }],
  },
  {
    name: 'tpl-lot',
    template_label: 'Lot photograph',
    template_name: 'lot_photograph',
    template_type: 'Marketing',
    language: 'en',
    status: 'Approved',
    header_type: 'Image',
    header_media: photo('Alleppey', 'Lot 18'),
    mime_type: 'image/svg+xml',
    message: 'Hello {{1}}, the lot you asked about is attached.',
    footer: 'Sundarban Spices',
    whatsapp_account: SALES,
    variable_format: 'Positional',
    template_variables: [{ variable_name: '1', variable_example: 'Meera' }],
    buttons: [
      { button_type: 'Quick Reply', button_text: 'Reserve it' },
      { button_type: 'URL', button_text: 'Open the sheet', url: 'https://example.com/lots/{{1}}' },
    ],
  },
]

const profiles: Profile[] = [
  { name: 'prf-meera', profile_name: 'Meera Iyer', phone_number: '+91 98450 22119', whatsapp_account: SALES, status: 'Active' },
  { name: 'prf-rafiq', profile_name: 'Rafiq Traders', phone_number: '+91 33 4065 1180', whatsapp_account: DISPATCH, status: 'Active' },
  { name: 'prf-anita', profile_name: 'Anita Desai', phone_number: '+91 98200 44110', whatsapp_account: SALES, status: 'Active' },
  { name: 'prf-hotel', profile_name: 'Hotel Grand Chowringhee', phone_number: '+91 33 2223 8890', whatsapp_account: SALES, status: 'Blocked' },
  { name: 'prf-arjun', profile_name: 'Arjun Patel', phone_number: '+91 98250 44218', whatsapp_account: DISPATCH, status: 'Active' },
]

function message(partial: ChatMessage): ChatMessage {
  return partial
}

const threads: Record<string, ChatMessage[]> = {
  'prf-meera': [
    message({
      name: 'msg-meera-1',
      to: 'prf-meera',
      direction: 'Incoming',
      message: 'Can you hold 20 kg of the Alleppey green for us?',
      creation: ago(80),
      status: 'Read',
      message_id: 'wamid.meera.1',
      reference_doctype: 'Sales Order',
      reference_docname: 'SAL-ORD-0042',
    }),
    message({
      name: 'msg-meera-2',
      to: 'prf-meera',
      direction: 'Outgoing',
      message: 'Held until Friday. The lot photo is attached.',
      creation: ago(70),
      status: 'Read',
      message_id: 'wamid.meera.2',
      mime_type: 'image/svg+xml',
      media_url: photo('Alleppey green', 'Lot 18 · 20 kg'),
      file_name: 'lot-18.svg',
      reference_doctype: 'Sales Order',
      reference_docname: 'SAL-ORD-0042',
      context_message_id: 'wamid.meera.1',
    }),
    message({
      name: 'msg-meera-3',
      to: 'prf-meera',
      direction: 'Incoming',
      message: 'Please send the quotation on the order.',
      creation: ago(18),
      status: 'Read',
      message_id: 'wamid.meera.3',
      reference_doctype: 'Sales Order',
      reference_docname: 'SAL-ORD-0042',
    }),
  ],
  'prf-rafiq': [
    message({
      name: 'msg-rafiq-1',
      to: 'prf-rafiq',
      direction: 'Incoming',
      message: 'Has the pepper consignment left?',
      creation: ago(23 * 60 + 10),
      status: 'Read',
      message_id: 'wamid.rafiq.1',
      reference_doctype: 'Delivery Note',
      reference_docname: 'MAT-DN-0194',
    }),
    message({
      name: 'msg-rafiq-2',
      to: 'prf-rafiq',
      direction: 'Outgoing',
      is_template: true,
      whatsapp_template: 'tpl-dispatch',
      template: 'Your order MAT-DN-0194 has left the warehouse and is due tomorrow morning.',
      template_label: 'Dispatch notice',
      footer: 'Sundarban Spices',
      buttons: [{ button_type: 'URL', button_text: 'Track', url: 'https://example.com/track' }],
      creation: ago(23 * 60),
      status: 'Delivered',
      message_id: 'wamid.rafiq.2',
      reference_doctype: 'Delivery Note',
      reference_docname: 'MAT-DN-0194',
    }),
  ],
  'prf-anita': [
    message({
      name: 'msg-anita-1',
      to: 'prf-anita',
      direction: 'Incoming',
      message: 'We liked the sample tin. What is the carton price?',
      creation: ago(60 * 30),
      status: 'Read',
      message_id: 'wamid.anita.1',
    }),
    message({
      name: 'msg-anita-2',
      to: 'prf-anita',
      direction: 'Outgoing',
      message: 'Following up on the carton price.',
      creation: ago(60 * 6),
      status: 'Failed',
      error_code: '131047',
      error_message: 'More than 24 hours have passed since the customer last replied. Send an approved template.',
      message_id: 'wamid.anita.2',
    }),
  ],
  'prf-hotel': [
    message({
      name: 'msg-hotel-1',
      to: 'prf-hotel',
      direction: 'Incoming',
      message: 'Please stop the weekly offers.',
      creation: ago(60 * 24 * 4),
      status: 'Read',
      message_id: 'wamid.hotel.1',
    }),
  ],
  'prf-arjun': [
    message({
      name: 'msg-arjun-1',
      to: 'prf-arjun',
      direction: 'Outgoing',
      is_template: true,
      whatsapp_template: 'tpl-price',
      template: 'Cardamom and black pepper are ready to book. Reply if you want the sheet.',
      header: 'This week’s lots',
      template_label: 'Price list',
      buttons: [{ button_type: 'Quick Reply', button_text: 'Send the sheet' }],
      creation: ago(60 * 5),
      status: 'Sent',
      message_id: 'wamid.arjun.1',
    }),
  ],
}

function summarize(profile: Profile, rows: ChatMessage[]): Conversation {
  const visible = rows.filter((row) => !row.reaction)
  const preview = visible[visible.length - 1] || null
  const window = serviceWindow(rows)
  let conversation_status: Conversation['conversation_status'] = 'template_only'
  if (profile.status === 'Blocked') conversation_status = 'blocked'
  else if (preview?.status === 'Failed') conversation_status = 'failed'
  else if (preview?.direction === 'Incoming') conversation_status = 'needs_reply'
  else if (window.status === 'open') conversation_status = 'window_open'
  return {
    profile,
    preview,
    window,
    conversation_status,
    needs_reply: conversation_status === 'needs_reply',
    failed: conversation_status === 'failed',
    assignment: {
      assignment_status: profile.status === 'Blocked' ? 'Closed' : 'Unassigned',
      assignee: null,
      priority: 'Medium',
    },
  }
}

export function sampleInbox(): Inbox {
  return {
    mode: 'sample',
    connected: true,
    user: 'Administrator',
    site: null,
    default_account: SALES,
    can_read_logs: true,
    accounts,
    templates,
    conversations: profiles.map((profile) => summarize(profile, threads[profile.name] || [])),
  }
}

export function sampleThread(profileName: string): Thread | null {
  const profile = profiles.find((row) => row.name === profileName)
  if (!profile) return null
  const messages = (threads[profileName] || []).map((row) => ({ ...row, reactions: row.reactions || [] }))
  const references = uniqueRefs(messages)
  return {
    profile,
    messages,
    window: serviceWindow(messages),
    references,
    links: references,
  }
}

function uniqueRefs(messages: ChatMessage[]) {
  const seen = new Set<string>()
  const refs = []
  for (const message of messages) {
    if (!message.reference_doctype || !message.reference_docname) continue
    const key = `${message.reference_doctype}:${message.reference_docname}`
    if (seen.has(key)) continue
    seen.add(key)
    refs.push({ doctype: message.reference_doctype, docname: message.reference_docname, title: message.reference_docname })
  }
  return refs
}

export function sampleLogs(): LogRow[] {
  return [
    {
      name: 'log-1',
      level: 'Error',
      event_type: 'Message',
      timestamp: ago(60 * 6),
      account: SALES,
      reference_doctype: 'WA Message',
      reference_docname: 'msg-anita-2',
      message: 'Meta rejected the text. Reopen the conversation with an approved template.',
      response_data: '{ "error": { "code": 131047 } }',
    },
    {
      name: 'log-2',
      level: 'Info',
      event_type: 'Webhook',
      timestamp: ago(18),
      account: SALES,
      message: 'Inbound message stored for Meera Iyer.',
    },
    {
      name: 'log-3',
      level: 'Info',
      event_type: 'Template',
      timestamp: ago(60 * 5),
      account: DISPATCH,
      message: 'Price list accepted by Meta and marked Approved.',
    },
  ]
}

export function rememberSampleMessage(profileName: string, row: ChatMessage) {
  threads[profileName] = [...(threads[profileName] || []), row]
}
