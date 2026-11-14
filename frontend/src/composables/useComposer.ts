import { computed, reactive, ref, watch } from 'vue'
import type {
  MediaFile,
  MessagesController,
  SendMessagePayload,
  WhatsAppContentType,
  WhatsAppMessage,
} from '@whatsapp/ui/components/Messages'
import { useDesk } from '@/stores/desk'
import { toWhatsAppMessages } from '@/utils/whatsappMessage'
import type { WindowState } from '@/types'

function mimeFor(type: WhatsAppContentType, fileUrl?: string) {
  const fromDataUrl = /^data:([^;,]+)/.exec(fileUrl || '')?.[1]
  if (fromDataUrl) return fromDataUrl
  if (type === 'image') return 'image/jpeg'
  if (type === 'video') return 'video/mp4'
  if (type === 'audio') return 'audio/mpeg'
  if (type === 'document') return 'application/octet-stream'
  return 'text/plain'
}

function serviceWindowOf(window: WindowState | null) {
  if (!window) return null
  return {
    status: window.status,
    expiresAt: window.expires_at ? new Date(window.expires_at) : null,
  }
}

/**
 * `MessageInput` reads a `MessagesController`. `useMessages()` is reference-document
 * scoped and calls the WhatsApp APIs itself, so the desk keeps profile-scoped sends
 * and sample mode behind this adapter.
 */
export function useDeskComposer(): MessagesController {
  const desk = useDesk()
  const draft = ref('')
  const pendingMedia = ref<MediaFile>()
  const pendingType = ref<WhatsAppContentType>('document')
  const replyTo = ref<WhatsAppMessage | null>(null)
  const error = ref<unknown>(null)

  const messages = computed(() => toWhatsAppMessages(desk.thread.value?.messages || []))
  const serviceWindow = computed(() => serviceWindowOf(desk.windowState.value))
  const canSend = computed(() => !desk.sending.value && Boolean(draft.value.trim() || pendingMedia.value))

  watch(
    () => desk.profile.value,
    () => {
      draft.value = ''
      pendingMedia.value = undefined
      pendingType.value = 'document'
      replyTo.value = null
      error.value = null
    },
  )

  function setDraft(text: string) {
    draft.value = text
  }

  watch(draft, (value) => {
    if (value.trim()) desk.announceTyping()
  })

  function setReplyTo(message: WhatsAppMessage) {
    replyTo.value = message
  }

  function clearReply() {
    replyTo.value = null
  }

  function attach(file: MediaFile, type: WhatsAppContentType = 'document') {
    pendingMedia.value = file
    pendingType.value = type
  }

  function clearAttachment() {
    pendingMedia.value = undefined
    pendingType.value = 'document'
  }

  function buildPayload(overrides?: Pick<SendMessagePayload, 'message'>): SendMessagePayload | null {
    const message = overrides?.message ?? draft.value
    const attachment = pendingMedia.value
    if (!message.trim() && !attachment) return null
    return {
      message,
      attach: attachment?.file_url,
      contentType: attachment ? pendingType.value : 'text',
      replyTo: replyTo.value?.name,
    }
  }

  function reset() {
    draft.value = ''
    clearAttachment()
    replyTo.value = null
  }

  async function send(overrides?: Pick<SendMessagePayload, 'message'>): Promise<string | null> {
    const payload = buildPayload(overrides)
    const file = pendingMedia.value
    if (!payload) return null
    error.value = null
    try {
      if (payload.attach) {
        const name = await desk.sendMedia(
          { file_url: payload.attach, file_name: file?.file_name },
          mimeFor(payload.contentType, payload.attach),
          payload.message,
          payload.replyTo,
        )
        if (!name) return null
        clearAttachment()
        clearReply()
        return name
      }
      const name = await desk.sendText(payload.message, payload.replyTo)
      if (!name) return null
      reset()
      return name
    } catch (caught) {
      error.value = caught
      return null
    }
  }

  async function react(messageName: string, emoji: string) {
    error.value = null
    try {
      return await desk.react(messageName, emoji)
    } catch (caught) {
      error.value = caught
      return null
    }
  }

  async function reload() {
    if (desk.profile.value) await desk.openProfile(desk.profile.value)
  }

  return reactive({
    messages,
    loading: computed(() => desk.threadLoading.value),
    sending: desk.sending,
    error,
    serviceWindow,
    reload,
    send,
    react,
    draft,
    pendingMedia,
    pendingType,
    replyTo,
    canSend,
    setDraft,
    setReplyTo,
    clearReply,
    attach,
    clearAttachment,
    buildPayload,
    reset,
  }) as MessagesController
}
