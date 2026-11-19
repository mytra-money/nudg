export interface Profile {
  name: string
  profile_name: string
  phone_number: string
  whatsapp_account: string
  status: 'Active' | 'Blocked' | 'Archived'
  wa_id?: string
}

export interface Account {
  name: string
  account_name: string
  status: 'Active' | 'Inactive'
  auto_read_receipts?: boolean
  is_default?: boolean
}

export interface TemplateButton {
  button_type: string
  button_text: string
  url?: string
  phone_number?: string
}

export interface TemplateVariable {
  variable_name: string
  variable_example?: string
  variable_field?: string
}

export interface Template {
  name: string
  template_label: string
  template_name?: string
  template_type: string
  language: string
  status: string
  header_text?: string
  header_type?: string
  header_media?: string
  mime_type?: string
  message: string
  footer?: string
  reference_doctype?: string
  whatsapp_account?: string
  variable_format?: string
  template_variables?: TemplateVariable[]
  buttons: TemplateButton[]
}

export interface AssignmentInfo {
  name?: string
  assignee?: string | null
  /** Every person with an open Frappe assignment on this conversation. */
  assignees?: string[]
  assignment_status: 'Unassigned' | 'Assigned' | 'Closed' | string
  priority?: string
  assignment_source?: string | null
  last_assigned_on?: string | null
}

export interface ChatMessage {
  name: string
  to: string
  direction: 'Incoming' | 'Outgoing'
  message?: string
  creation: string
  status?: string
  is_template?: boolean
  whatsapp_template?: string
  template?: string
  template_label?: string
  header?: string
  footer?: string
  buttons?: TemplateButton[]
  mime_type?: string
  media_url?: string
  file_name?: string
  reaction?: string | null
  reactions?: { emoji: string; direction: string }[]
  reply_to?: string
  reply_message?: string
  reply_to_direction?: string
  reference_doctype?: string
  reference_docname?: string
  error_code?: string
  error_message?: string
  message_id?: string
  context_message_id?: string
  whatsapp_account?: string
}

export interface WindowState {
  status: 'open' | 'closed' | 'unopened'
  expires_at: string | null
  last_incoming_at: string | null
}

export interface DocLink {
  doctype: string
  docname: string
  title?: string
}

/** Primary inbox filter field. Maintained by the desk API from WA Profile / WA Message / window. */
export type ConversationStatus =
  | 'blocked'
  | 'failed'
  | 'needs_reply'
  | 'window_open'
  | 'template_only'

export interface Conversation {
  profile: Profile
  preview: ChatMessage | null
  window: WindowState
  /** Single status field used by the inbox filter. */
  conversation_status: ConversationStatus
  needs_reply: boolean
  failed: boolean
  assignment?: AssignmentInfo
}

export interface Inbox {
  mode: 'live' | 'sample'
  connected: boolean
  user: string
  site: string | null
  default_account: string | null
  can_read_logs: boolean
  accounts: Account[]
  templates: Template[]
  conversations: Conversation[]
}

export interface ConversationNote {
  name: string
  content: string
  author: string
  creation: string
}

export interface Thread {
  profile: Profile
  messages: ChatMessage[]
  notes?: ConversationNote[]
  window: WindowState
  references: DocLink[]
  links: DocLink[]
}

export interface IntegrationStatus {
  whatsapp_installed: boolean
  doctypes_ready: boolean
  missing_dependencies: string[]
  default_account: string | null
  active_account_count: number | null
  detail: string
}

export interface LogRow {
  name: string
  level: string
  event_type: string
  timestamp: string
  account?: string
  reference_doctype?: string
  reference_docname?: string
  message: string
  request_data?: string
  response_data?: string
}
