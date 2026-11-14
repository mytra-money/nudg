import { computed, ref } from 'vue'
import { call, toast } from 'frappe-ui'
import { conversationStatusOf } from '@/conversationStatus'
import { contentKind, errorText, serviceWindow } from '@/format'
import { rememberSampleMessage, sampleInbox, sampleLogs, sampleThread, templates as sampleTemplates } from '@/sample'
import type { ChatMessage, Inbox, LogRow, Template, Thread } from '@/types'

const inbox = ref<Inbox | null>(null)
const thread = ref<Thread | null>(null)
const logs = ref<LogRow[]>([])
const profile = ref<string | null>(null)
const loading = ref(true)
const threadLoading = ref(false)
const sending = ref(false)
const error = ref<string | null>(null)
const presence = ref<Record<string, { user: string; name: string; typing: boolean; viewing: boolean }[]>>({})

let started = false
let typingTimer: ReturnType<typeof setTimeout> | undefined
let typingSentFor: string | null = null

const account = ref('all')

export function playSound(type: 'send' | 'receive') {
  try {
    const url = type === 'send' ? '/assets/frappe/sounds/submit.mp3' : '/assets/frappe/sounds/alert.mp3'
    const audio = new Audio(url)
    audio.volume = 0.3
    void audio.play().catch(() => {})
  } catch {
    // browser autoplay policy
  }
}

export const isManager = computed(() => {
  if (typeof window === 'undefined') return true
  if (window.is_manager !== undefined) return Boolean(window.is_manager)
  if (Array.isArray(window.roles)) {
    return (
      window.roles.includes('WhatsApp Manager') ||
      window.roles.includes('System Manager') ||
      window.user === 'Administrator'
    )
  }
  if (!window.csrf_token) return true
  return false
})

function live() {
  return Boolean(window.csrf_token)
}

function syncTabTitle() {
  if (typeof document === 'undefined') return
  const waiting = (inbox.value?.conversations || []).filter((row) => conversationStatusOf(row) === 'needs_reply').length
  document.title = waiting ? `(${waiting}) NUDG` : 'NUDG'
}

function applyPresence(data: any, kind: 'typing' | 'viewing') {
  const id = String(data?.conversation_id || '')
  const actor = String(data?.user || '')
  if (!id || !actor || actor === window.user) return
  const current = presence.value[id] || []
  const others = current.filter((row) => row.user !== actor)
  if (data.active) {
    const previous = current.find((row) => row.user === actor)
    others.push({
      user: actor,
      name: data.user_fullname || actor,
      typing: kind === 'typing' ? true : Boolean(previous?.typing),
      viewing: kind === 'viewing' ? true : Boolean(previous?.viewing),
    })
  }
  presence.value = { ...presence.value, [id]: others }
}

function announcePresence(conversationId: string | null, action: 'typing' | 'viewing' | 'stopped_typing' | 'leave') {
  if (!live() || !conversationId) return
  void call('nudg.api.publish_presence', {
    conversation_id: conversationId,
    action,
  }).catch(() => undefined)
}

function announceTyping() {
  const conversationId = profile.value
  if (!live() || !conversationId) return
  if (typingSentFor !== conversationId) {
    typingSentFor = conversationId
    announcePresence(conversationId, 'typing')
  }
  if (typingTimer) clearTimeout(typingTimer)
  typingTimer = setTimeout(() => {
    typingSentFor = null
    announcePresence(conversationId, 'stopped_typing')
  }, 2000)
}

function accountArg() {
  return account.value && account.value !== 'all' ? account.value : undefined
}

function recomputeSample(name: string) {
  const next = sampleThread(name)
  if (!next || !inbox.value) return
  thread.value = next
  inbox.value = {
    ...sampleInbox(),
    conversations: sampleInbox().conversations,
  }
}

export function useDesk() {
  const mode = computed(() => inbox.value?.mode || (live() ? 'live' : 'sample'))

  async function load() {
    if (started && inbox.value) return
    started = true
    loading.value = true
    error.value = null
    try {
      if (!live()) {
        inbox.value = sampleInbox()
        logs.value = sampleLogs()
        return
      }
      inbox.value = await call<Inbox>('nudg.api.get_inbox', { account: accountArg() })
      if (inbox.value.can_read_logs) {
        logs.value = await call<LogRow[]>('nudg.api.get_logs', { account: accountArg() })
      }
      if (typeof window !== 'undefined' && (window as any).frappe?.realtime) {
        const realtime = (window as any).frappe.realtime
        realtime.on('nudg_message', (data: any) => {
          if (data?.direction === 'Incoming') {
            playSound('receive')
            if (profile.value && (data.contact === profile.value || data.channel === profile.value)) {
              void openProfile(profile.value)
            }
            void refresh()
          }
        })
        realtime.on('whatsapp_inbox_update', () => {
          void refresh()
        })
        realtime.on('nudg_agent_typing', (data: any) => applyPresence(data, 'typing'))
        realtime.on('nudg_agent_viewing', (data: any) => applyPresence(data, 'viewing'))
      }
    } catch (caught) {
      error.value = errorText(caught)
    } finally {
      loading.value = false
      syncTabTitle()
    }
  }

  async function refresh() {
    if (!live()) return
    try {
      inbox.value = await call<Inbox>('nudg.api.get_inbox', { account: accountArg() })
      if (profile.value) {
        thread.value = await call<Thread>('nudg.api.get_thread', { profile: profile.value })
      }
      syncTabTitle()
    } catch (caught) {
      toast.error(errorText(caught))
    }
  }

  async function setAccount(name: string) {
    account.value = name || 'all'
    const selected = accountArg()
    if (thread.value && selected && thread.value.profile.whatsapp_account !== selected) {
      profile.value = null
      thread.value = null
    }
    if (!live() || !inbox.value) return
    try {
      inbox.value = await call<Inbox>('nudg.api.get_inbox', { account: selected })
      syncTabTitle()
      if (inbox.value.can_read_logs) {
        logs.value = await call<LogRow[]>('nudg.api.get_logs', { account: selected })
      }
    } catch (caught) {
      toast.error(errorText(caught))
    }
  }

  async function openProfile(name: string | null) {
    const previous = profile.value
    if (previous && previous !== name) announcePresence(previous, 'leave')
    profile.value = name
    thread.value = null
    if (!name) return
    if (!live()) {
      thread.value = sampleThread(name)
      return
    }
    announcePresence(name, 'viewing')
    threadLoading.value = true
    try {
      thread.value = await call<Thread>('nudg.api.get_thread', { profile: name })
    } catch (caught) {
      toast.error(errorText(caught))
    } finally {
      threadLoading.value = false
    }
  }

  function quoted(name?: string) {
    if (!name || !thread.value) return undefined
    return thread.value.messages.find((message) => message.name === name)
  }

  async function sendText(body: string, replyTo?: string): Promise<string | null> {
    if (!profile.value || !thread.value) return null
    const text = body.trim()
    if (!text) return null
    const target = quoted(replyTo)
    if (!live()) {
      const window = thread.value.window
      const failed = window.status !== 'open'
      const row: ChatMessage = {
        name: `local-${Date.now()}`,
        to: profile.value,
        direction: 'Outgoing',
        message: text,
        creation: new Date().toISOString(),
        status: failed ? 'Failed' : 'Sent',
        reply_to: replyTo,
        reply_message: target?.template || target?.message,
        reply_to_direction: target?.direction,
        context_message_id: replyTo ? target?.message_id || replyTo : undefined,
        message_id: `wamid.local.${Date.now()}`,
        error_code: failed ? '131047' : undefined,
        error_message: failed ? 'Template required' : undefined,
      }
      rememberSampleMessage(profile.value, row)
      recomputeSample(profile.value)
      if (failed) toast.error('Template required')
      return row.name
    }
    sending.value = true
    try {
      const reference = thread.value.references[0]
      const result = await call('whatsapp.whatsapp.api.messages.send_message', {
        to: profile.value,
        message: text,
        reply_to: replyTo,
        reference_doctype: reference?.doctype,
        reference_docname: reference?.docname,
      })
      await openProfile(profile.value)
      inbox.value = await call<Inbox>('nudg.api.get_inbox', { account: accountArg() })
      syncTabTitle()
      playSound('send')
      return typeof result === 'string' && result ? result : 'sent'
    } catch (caught) {
      toast.error(errorText(caught))
      return null
    } finally {
      sending.value = false
    }
  }

  async function sendMedia(
    file: { file_url: string; file_name?: string },
    mime: string,
    caption: string,
    replyTo?: string,
  ): Promise<string | null> {
    if (!profile.value || !thread.value || !file.file_url) return null
    const target = quoted(replyTo)
    if (!live()) {
      const failed = thread.value.window.status !== 'open'
      const row: ChatMessage = {
        name: `local-${Date.now()}`,
        to: profile.value,
        direction: 'Outgoing',
        message: caption,
        creation: new Date().toISOString(),
        status: failed ? 'Failed' : 'Sent',
        media_url: file.file_url,
        mime_type: mime,
        file_name: file.file_name,
        reply_to: replyTo,
        reply_message: target?.template || target?.message,
        reply_to_direction: target?.direction,
        context_message_id: replyTo ? target?.message_id || replyTo : undefined,
        message_id: `wamid.local.${Date.now()}`,
        error_code: failed ? '131047' : undefined,
        error_message: failed ? 'Template required' : undefined,
      }
      rememberSampleMessage(profile.value, row)
      recomputeSample(profile.value)
      if (failed) toast.error('Template required')
      return row.name
    }
    sending.value = true
    try {
      const reference = thread.value.references[0]
      const result = await call('whatsapp.whatsapp.api.messages.send_message', {
        to: profile.value,
        message: caption,
        attach: file.file_url,
        content_type: contentKind(mime),
        reply_to: replyTo,
        reference_doctype: reference?.doctype,
        reference_docname: reference?.docname,
      })
      await openProfile(profile.value)
      playSound('send')
      return typeof result === 'string' && result ? result : 'sent'
    } catch (caught) {
      toast.error(errorText(caught))
      return null
    } finally {
      sending.value = false
    }
  }

  async function sendTemplate(template: Template) {
    if (!profile.value || !thread.value) return
    if (template.status !== 'Approved') {
      toast.error('Meta has not approved this template yet.')
      return
    }
    if (!live()) {
      const source = sampleTemplates.find((row) => row.name === template.name) || template
      const row: ChatMessage = {
        name: `local-${Date.now()}`,
        to: profile.value,
        direction: 'Outgoing',
        is_template: true,
        whatsapp_template: source.name,
        template: source.message,
        header: source.header_text,
        footer: source.footer,
        buttons: source.buttons,
        template_label: source.template_label,
        creation: new Date().toISOString(),
        status: 'Sent',
      }
      rememberSampleMessage(profile.value, row)
      recomputeSample(profile.value)
      toast.success('Template queued in the sample thread')
      return
    }
    sending.value = true
    try {
      const reference = thread.value.references[0]
      await call('whatsapp.whatsapp.api.messages.send_template', {
        template: template.name,
        to: profile.value,
        reference_doctype: reference?.doctype,
        reference_docname: reference?.docname,
      })
      await openProfile(profile.value)
      playSound('send')
      toast.success('Template sent')
    } catch (caught) {
      toast.error(errorText(caught))
    } finally {
      sending.value = false
    }
  }

  async function react(messageName: string, emoji: string): Promise<string | null> {
    if (!profile.value || !thread.value) return null
    if (!live()) {
      const target = thread.value.messages.find((message) => message.name === messageName)
      if (!target) return null
      target.reactions = [{ emoji, direction: 'Outgoing' }]
      thread.value = { ...thread.value, messages: [...thread.value.messages] }
      return messageName
    }
    try {
      const result = await call('whatsapp.whatsapp.api.messages.react_to_message', {
        message: messageName,
        emoji,
      })
      await openProfile(profile.value)
      return typeof result === 'string' && result ? result : messageName
    } catch (caught) {
      toast.error(errorText(caught))
      return null
    }
  }

  function simulateReply() {
    if (live() || !profile.value || !thread.value) return
    const row: ChatMessage = {
      name: `local-in-${Date.now()}`,
      to: profile.value,
      direction: 'Incoming',
      message: 'Yes, that works. Please go ahead.',
      creation: new Date().toISOString(),
      status: 'Read',
      message_id: `wamid.local.${Date.now()}`,
    }
    rememberSampleMessage(profile.value, row)
    recomputeSample(profile.value)
  }

  const windowState = computed(() => (thread.value ? serviceWindow(thread.value.messages) : null))

  return {
    inbox,
    account,
    thread,
    logs,
    profile,
    loading,
    threadLoading,
    sending,
    error,
    mode,
    windowState,
    presence,
    load,
    setAccount,
    refresh,
    openProfile,
    sendText,
    sendMedia,
    sendTemplate,
    react,
    simulateReply,
    announceTyping,
  }
}
