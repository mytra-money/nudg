import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { call, createResource, toast } from 'frappe-ui'
import { contentKind, errorText, serviceWindow } from '@/utils/format'
import {
  rememberSampleMessage,
  sampleInbox,
  sampleThread,
  templates as sampleTemplates,
} from '@/mocks/sample'
import { useInboxStore } from '@/stores/inbox'
import { eventTargets, mergeLiveThread, type InboxLiveEvent } from '@/stores/inboxLive'
import { isLiveSession } from '@/stores/session'
import { playSound } from '@/stores/sounds'
import { getSocket } from '@/socket'
import { deskCacheKey, threadAccountAllowed } from '@/utils/deskCache'
import type { ChatMessage, ConversationNote, Template, Thread } from '@/types'

export const useThreadStore = defineStore('nudg-thread', () => {
  const profile = ref<string | null>(null)
  const sending = ref(false)
  let typingTimer: ReturnType<typeof setTimeout> | undefined
  let typingSentFor: string | null = null

  const threadResource = createResource<Thread | null>({
    url: 'nudg.api.get_thread',
    cache: deskCacheKey('thread'),
    initialData: null,
    auto: false,
  })

  const thread = computed({
    get: () => threadResource.data,
    set: (value) => {
      threadResource.setData(value)
    },
  })

  const threadLoading = computed(() => threadResource.loading)
  const windowState = computed(() => (thread.value ? serviceWindow(thread.value.messages) : null))

  // IndexedDB can restore the previous login's thread after this store is created.
  // Drop it once the inbox shows that WhatsApp account is not this user's.
  watch(
    () => [useInboxStore().inbox?.accounts, threadResource.data?.profile?.whatsapp_account] as const,
    ([accounts, account]) => {
      if (!accounts || !threadResource.data) return
      if (threadAccountAllowed(account, accounts)) return
      profile.value = null
      threadResource.setData(null)
    },
  )

  function announcePresence(
    conversationId: string | null,
    action: 'typing' | 'viewing' | 'stopped_typing' | 'leave',
  ) {
    if (!isLiveSession() || !conversationId) return
    void call('nudg.api.publish_presence', {
      conversation_id: conversationId,
      action,
    }).catch(() => undefined)
  }

  function announceTyping() {
    const conversationId = profile.value
    if (!isLiveSession() || !conversationId) return
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

  function setThreadNotes(notes: ConversationNote[]) {
    const current = threadResource.data
    if (!current) return
    threadResource.setData({ ...current, notes })
  }

  function recomputeSample(name: string) {
    const inbox = useInboxStore()
    const next = sampleThread(name)
    if (!next || !inbox.inbox) return
    threadResource.setData(next)
    inbox.inboxResource.setData({
      ...sampleInbox(),
      conversations: sampleInbox().conversations,
    })
  }

  function applyLive(event: InboxLiveEvent) {
    const open = profile.value
    if (!eventTargets(open, event) || !open) return
    const current = threadResource.data
    if (!current || current.profile.name !== open) {
      void syncOpen()
      return
    }
    const next = mergeLiveThread(current, open, event)
    if (next !== current) threadResource.setData(next)
    const arrived = event.message?.name || event.conversation?.preview?.name
    if (arrived && !next.messages.some((row) => row.name === arrived)) void syncOpen()
  }

  async function loadOlder() {
    const name = profile.value
    const current = threadResource.data
    if (!name || !current?.has_older || !isLiveSession()) return
    const oldest = current.messages[0]?.creation
    if (!oldest) return
    const page = await call<Thread>('nudg.api.get_thread', {
      profile: name,
      before_creation: oldest,
      limit: 40,
    })
    const seen = new Set(current.messages.map((row) => row.name))
    const older = (page?.messages || []).filter((row) => row.name && !seen.has(row.name))
    threadResource.setData({
      ...current,
      messages: [...older, ...current.messages],
      has_older: Boolean(page?.has_older),
    })
  }

  /** Replace the open thread from the server without clearing what is already on screen. */
  async function syncOpen() {
    const name = profile.value
    if (!name || !isLiveSession()) return
    try {
      await threadResource.fetch({ profile: name })
    } catch {
      // Keep the messages already rendered.
    }
  }

  async function confirmIfOffline() {
    await syncOpen()
    if (getSocket()?.connected) return
    await useInboxStore().refresh({ silent: true })
  }

  async function openProfile(name: string | null) {
    const previous = profile.value
    if (previous && previous !== name) announcePresence(previous, 'leave')
    profile.value = name
    threadResource.setData(null)
    if (!name) return
    if (!isLiveSession()) {
      threadResource.setData(sampleThread(name))
      return
    }
    announcePresence(name, 'viewing')
    try {
      await threadResource.fetch({ profile: name })
      useInboxStore().markRead(name)
    } catch (caught) {
      toast.error(errorText(caught))
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
    if (!isLiveSession()) {
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
      playSound('send')
      await confirmIfOffline()
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
    if (!isLiveSession()) {
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
      playSound('send')
      await confirmIfOffline()
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
    if (!isLiveSession()) {
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
      playSound('send')
      await confirmIfOffline()
      toast.success('Template sent')
    } catch (caught) {
      toast.error(errorText(caught))
    } finally {
      sending.value = false
    }
  }

  async function react(messageName: string, emoji: string): Promise<string | null> {
    if (!profile.value || !thread.value) return null
    if (!isLiveSession()) {
      const target = thread.value.messages.find((message) => message.name === messageName)
      if (!target) return null
      target.reactions = [{ emoji, direction: 'Outgoing' }]
      threadResource.setData({ ...thread.value, messages: [...thread.value.messages] })
      return messageName
    }
    try {
      const result = await call('whatsapp.whatsapp.api.messages.react_to_message', {
        message: messageName,
        emoji,
      })
      await confirmIfOffline()
      return typeof result === 'string' && result ? result : messageName
    } catch (caught) {
      toast.error(errorText(caught))
      return null
    }
  }

  function simulateReply() {
    if (isLiveSession() || !profile.value || !thread.value) return
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

  return {
    thread,
    profile,
    threadLoading,
    sending,
    windowState,
    threadResource,
    openProfile,
    applyLive,
    syncOpen,
    loadOlder,
    setThreadNotes,
    sendText,
    sendMedia,
    sendTemplate,
    react,
    simulateReply,
    announceTyping,
    announcePresence,
  }
})
