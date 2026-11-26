<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, Dialog, FormControl, Select, TextInput, call, toast } from 'frappe-ui'
import { MessageInput, MessageList } from '@whatsapp/ui/components/Messages'
import type { ReactPayload, WhatsAppMessage } from '@whatsapp/ui/components/Messages'
import DeskTemplatePreview from '@/components/DeskTemplatePreview.vue'
import ProfileDetails from '@/components/ProfileDetails.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import BotHandoffBanner from '@/components/inbox/BotHandoffBanner.vue'
import CannedReplyPicker from '@/components/inbox/CannedReplyPicker.vue'
import ChatHeader from '@/components/inbox/ChatHeader.vue'
import ConversationList from '@/components/inbox/ConversationList.vue'
import {
  CONVERSATION_STATUS_FILTERS,
  conversationStatusAt,
  conversationStatusOf,
} from '@/utils/conversationStatus'
import { useDeskComposer } from '@/composables/useComposer'
import { applyQuickReplyDraft, slashCommand } from '@/utils/cannedReply'
import { displayTitle } from '@/utils/titles'
import { previewText, serviceWindow } from '@/utils/format'
import { userFacingError } from '@/utils/errors'
import { useDesk } from '@/stores/desk'
import {
  assignConversation,
  listAssignableUsers,
  listCatalogItems,
  listQuickReplies,
  sendCatalogProduct,
  unassignConversation,
  useQuickReply,
} from '@/services/catalogApi'
import { errorText } from '@/utils/format'
import { fetchDirectoryAccess, saveDirectoryProfile } from '@/services/directoryApi'
import { bootDirectoryAccess } from '@/utils/directoryAccess'
import { threadAccountAllowed } from '@/utils/deskCache'
import { labelForAccount } from '@/utils/accountSelection'
import { sessionUser as readSessionUser, userLabel } from '@/utils/frappeSession'
import type { Conversation, ConversationNote, Template } from '@/types'

const desk = useDesk()
const route = useRoute()
const composer = useDeskComposer()
const query = ref('')
const filter = ref<'all' | ReturnType<typeof conversationStatusOf>>('all')
const assignFilter = ref('all')
const filterUsers = ref<Array<{ value: string; label: string }>>([])

const details = ref(false)
const CONTACT_KEY = 'nudg.contact_sidebar'
const contactOpen = ref(typeof localStorage !== 'undefined' ? localStorage.getItem(CONTACT_KEY) !== '0' : true)
watch(contactOpen, (value) => {
  try {
    localStorage.setItem(CONTACT_KEY, value ? '1' : '0')
  } catch {
    /* ignore quota / private mode */
  }
})
const chatSearchOpen = ref(false)
const chatQuery = ref('')
const matchCursor = ref(0)
const desktopProfile = ref<{ openAssign: () => void } | null>(null)
const drawerProfile = ref<{ openAssign: () => void } | null>(null)
const templateOpen = ref(false)
const templateQuery = ref('')
const templateTypeFilter = ref<'all' | 'Utility' | 'Marketing'>('all')

const pickerManual = ref(false)
const pickerQuery = ref('')
const quickLoading = ref(false)
const quickReplies = ref<any[]>([])
const pickerRef = ref<InstanceType<typeof CannedReplyPicker> | null>(null)
const composerRoot = ref<HTMLElement | null>(null)
const notesOpen = ref(false)
const noteText = ref('')
const savingNote = ref(false)
const notes = computed<ConversationNote[]>(() => desk.thread.value?.notes || [])
const presenceLabel = computed(() => {
  const id = desk.profile.value
  if (!id) return ''
  const rows = desk.presence.value[id] || []
  const typing = rows.filter((row) => row.typing).map((row) => row.name)
  const viewing = rows.filter((row) => row.viewing && !row.typing).map((row) => row.name)
  if (typing.length) return `${typing.join(', ')} ${typing.length === 1 ? 'is' : 'are'} typing`
  if (viewing.length) return `${viewing.join(', ')} ${viewing.length === 1 ? 'is viewing' : 'are viewing'} this conversation`
  return ''
})

async function saveNote() {
  const text = noteText.value.trim()
  if (!text || !desk.profile.value || desk.mode.value !== 'live') return
  savingNote.value = true
  try {
    const result = await call<{ notes: ConversationNote[] }>('nudg.desk_api.add_conversation_note', {
      profile: desk.profile.value,
      note_text: text,
    })
    noteText.value = ''
    desk.setThreadNotes(result.notes || [])
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    savingNote.value = false
  }
}

const catalogOpen = ref(false)
const catalogQuery = ref('')
const catalogLoading = ref(false)
const catalogSending = ref(false)
const catalogSendingItem = ref('')
const catalogError = ref('')
const catalogItems = ref<any[]>([])

const assignUser = ref('')
const directoryAccess = ref(bootDirectoryAccess())
const canCreateProfile = computed(() => {
  if (!window.csrf_token) return true
  return Boolean(directoryAccess.value?.profile.create)
})
const newProfileOpen = ref(false)
const newProfileSaving = ref(false)
const newProfile = ref({
  profile_name: '',
  phone_number: '',
})
const currentAccount = computed(() => {
  const selected = desk.account.value
  return selected && selected !== 'all' ? selected : ''
})
const currentAccountLabel = computed(() =>
  labelForAccount(desk.inbox.value?.accounts || [], currentAccount.value),
)
const picked = ref<Template | null>(null)
const scroller = ref<HTMLElement | null>(null)
const sessionUser = readSessionUser()
const now = ref(Date.now())
let clock = 0
onMounted(() => {
  clock = window.setInterval(() => {
    now.value = Date.now()
  }, 30000)
  if (window.csrf_token) {
    void fetchDirectoryAccess()
      .then((row) => {
        if (row?.profile) directoryAccess.value = row
      })
      .catch(() => {
        /* keep the boot permissions */
      })
  }
  void listAssignableUsers()
    .then((rows) => {
      filterUsers.value = Array.isArray(rows) ? rows : []
    })
    .catch(() => {
      filterUsers.value = []
    })
})
onUnmounted(() => {
  window.clearInterval(clock)
  document.removeEventListener('pointerdown', onQuickReplyPointerDown, true)
})

function rowStatus(row: Conversation) {
  return conversationStatusAt(row, now.value)
}

const filterOptions = CONVERSATION_STATUS_FILTERS.map((row) => ({
  label: row.label,
  value: row.value,
}))

function applyInboxTab(tab: string) {
  if (tab === 'all' || tab === 'needs_reply' || tab === 'window_open' || tab === 'unassigned') {
    selectQuickTab(tab)
  }
}

watch(
  () => route.query.tab,
  (tab) => applyInboxTab(String(tab || '')),
  { immediate: true },
)

function selectQuickTab(tab: 'all' | 'needs_reply' | 'window_open' | 'unassigned') {
  if (tab === 'all') {
    filter.value = 'all'
    assignFilter.value = 'all'
  } else if (tab === 'needs_reply') {
    filter.value = 'needs_reply'
    assignFilter.value = 'all'
  } else if (tab === 'window_open') {
    filter.value = 'window_open'
    assignFilter.value = 'all'
  } else if (tab === 'unassigned') {
    filter.value = 'all'
    assignFilter.value = 'unassigned'
  }
}

function assigneesOf(row: { assignment?: { assignee?: string | null; assignees?: string[]; assignment_status?: string } | null }) {
  const listed = (row.assignment?.assignees || []).filter((person): person is string => Boolean(person))
  if (listed.length) return listed
  const one = row.assignment?.assignee
  if (!one || row.assignment?.assignment_status === 'Unassigned') return []
  return [one]
}

const assignOptions = computed(() => [
  { label: 'Anyone', value: 'all' },
  { label: 'Assigned to me', value: 'mine' },
  { label: 'Unassigned', value: 'unassigned' },
  ...filterUsers.value
    .filter((row) => row.value && row.value !== sessionUser)
    .map((row) => ({ label: row.label || row.value, value: row.value })),
])

// Live counts for quick chips
function unreadCount(row: Conversation) {
  return Math.max(0, Number(row.unread_count || 0))
}

const allRows = computed(() => {
  const rows = [...(desk.inbox.value?.conversations || [])]
  rows.sort((a, b) => (b.preview?.creation || '').localeCompare(a.preview?.creation || ''))
  const selected = desk.account.value
  if (!selected) return rows
  return rows.filter((row) => row.profile.whatsapp_account === selected)
})
const conversations = computed(() => {
  const rows = allRows.value
  return rows.filter((row) => {
    const haystack = `${row.profile.profile_name} ${row.profile.phone_number} ${previewText(row.preview)}`.toLowerCase()
    if (query.value && !haystack.includes(query.value.toLowerCase())) return false
    const people = assigneesOf(row)
    if (assignFilter.value === 'mine' && !people.includes(sessionUser)) return false
    if (assignFilter.value === 'unassigned' && people.length) return false
    if (
      assignFilter.value !== 'all' &&
      assignFilter.value !== 'mine' &&
      assignFilter.value !== 'unassigned' &&
      !people.includes(assignFilter.value)
    ) {
      return false
    }
    if (filter.value === 'all') return true
    if (filter.value === 'window_open') return rowStatus(row) === 'window_open'
    return rowStatus(row) === filter.value
  })
})

const currentAssignment = computed(() => {
  const name = desk.profile.value
  if (!name) return null
  return desk.inbox.value?.conversations.find((row) => row.profile.name === name)?.assignment || null
})

const current = computed(() => {
  const thread = desk.thread.value
  if (!threadAccountAllowed(thread?.profile?.whatsapp_account, desk.inbox.value?.accounts)) return null
  return thread
})
const windowState = computed(() => {
  const messages = current.value?.messages
  if (!messages) return null
  return serviceWindow(messages, now.value)
})

const pinLatest = ref(true)
let shownProfile = ''
let ignoreScroll = false

function scrollToLatest() {
  const el = scroller.value
  if (!el || !pinLatest.value) {
    ignoreScroll = false
    return
  }
  ignoreScroll = true
  el.scrollTop = el.scrollHeight
  requestAnimationFrame(() => {
    ignoreScroll = false
  })
}

async function loadEarlier() {
  const el = scroller.value
  const before = el?.scrollHeight || 0
  await desk.loadOlder()
  await nextTick()
  if (!el) return
  el.scrollTop = el.scrollHeight - before
}

function onChatScroll() {
  if (ignoreScroll) return
  const el = scroller.value
  if (!el) return
  const gap = el.scrollHeight - el.scrollTop - el.clientHeight
  pinLatest.value = gap < 120
}

watch(
  () => [current.value?.profile.name || '', current.value?.messages.length || 0, current.value?.messages.at(-1)?.name || ''] as const,
  async ([name]) => {
    if (name !== shownProfile) {
      shownProfile = name
      pinLatest.value = true
    }
    await nextTick()
    scrollToLatest()
    requestAnimationFrame(scrollToLatest)
  },
  { flush: 'post', immediate: true },
)

function open(row: Conversation) {
  void desk.openProfile(row.profile.name)
}

function openNewProfile() {
  newProfile.value = {
    profile_name: '',
    phone_number: '',
  }
  newProfileOpen.value = true
}

async function createProfileFromChat() {
  const phone = newProfile.value.phone_number.trim()
  const account = currentAccount.value
  if (!phone) {
    toast.error('Enter a phone number.')
    return
  }
  if (!account) {
    toast.error('Select a WhatsApp number in the top bar first.')
    return
  }
  if (!window.csrf_token) {
    toast.error('Sign in on a Frappe site to create a contact.')
    return
  }
  newProfileSaving.value = true
  try {
    const saved = await saveDirectoryProfile({
      profile_name: newProfile.value.profile_name.trim(),
      phone_number: phone,
      whatsapp_account: account,
      status: 'Active',
    })
    newProfileOpen.value = false
    query.value = ''
    selectQuickTab('all')
    await desk.refresh()
    await desk.openProfile(saved.name)
    toast.success(saved.created ? 'Contact created.' : 'Opened the existing contact.')
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    newProfileSaving.value = false
  }
}

function clearSearch() {
  query.value = ''
  selectQuickTab('all')
}

function chooseTemplate(template: Template) {
  picked.value = template
}

async function sendPicked() {
  if (!picked.value) return
  await desk.sendTemplate(picked.value)
  templateOpen.value = false
}

const filteredTemplates = computed(() => {
  const account = currentAccount.value
  const list = desk.inbox.value?.templates || []
  return list.filter((t) => {
    if (account && t.whatsapp_account && t.whatsapp_account !== account) return false
    if (templateTypeFilter.value !== 'all' && t.template_type !== templateTypeFilter.value) return false
    if (!templateQuery.value.trim()) return true
    const term = templateQuery.value.toLowerCase()
    return (
      (t.template_label || '').toLowerCase().includes(term) ||
      (t.template_name || '').toLowerCase().includes(term) ||
      (t.message || '').toLowerCase().includes(term)
    )
  })
})

function onReact(payload: ReactPayload) {
  void desk.react(payload.messageName, payload.emoji)
}

const slash = computed(() => slashCommand(composer.draft || ''))
const pickerOpen = computed(() => pickerManual.value || Boolean(slash.value?.open))
const pickerFilter = computed(() => (slash.value?.open ? slash.value.query : pickerQuery.value))

async function ensureQuickReplies() {
  if (quickLoading.value || quickReplies.value.length) return
  quickLoading.value = true
  try {
    quickReplies.value = await listQuickReplies(desk.account.value || undefined)
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    quickLoading.value = false
  }
}

function onQuickReplyPointerDown(event: Event) {
  if (!pickerOpen.value) return
  const root = composerRoot.value
  const target = event.target
  if (root && target instanceof Node && root.contains(target)) return
  closePicker()
}

watch(pickerOpen, (open) => {
  if (open) void ensureQuickReplies()
  document.removeEventListener('pointerdown', onQuickReplyPointerDown, true)
  if (open) document.addEventListener('pointerdown', onQuickReplyPointerDown, true)
})

watch(
  () => desk.account.value,
  () => {
    quickReplies.value = []
  },
)

async function openQuickReplies() {
  pickerQuery.value = ''
  pickerManual.value = true
  await ensureQuickReplies()
}

function toggleQuickReplies() {
  if (pickerOpen.value) {
    closePicker()
    return
  }
  void openQuickReplies()
}

function closePicker() {
  pickerManual.value = false
  if (slash.value?.open) {
    composer.setDraft(applyQuickReplyDraft(composer.draft || '', ''))
  }
}

function onPickerQuery(value: string) {
  if (slash.value?.open) {
    const draft = composer.draft || ''
    const lines = draft.split('\n')
    const last = lines[lines.length - 1] ?? ''
    lines[lines.length - 1] = last.replace(/(^|\s)\/[^\s]*$/, `$1/${value}`)
    composer.setDraft(lines.join('\n'))
    return
  }
  pickerQuery.value = value
}

async function onPickReply(row: { name: string }) {
  try {
    const reply = await useQuickReply(row.name)
    if (slash.value?.open) {
      composer.setDraft(applyQuickReplyDraft(composer.draft || '', reply.body))
    } else {
      composer.setDraft(reply.body)
    }
    pickerManual.value = false
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

function onComposerKeydown(event: KeyboardEvent) {
  if (!pickerOpen.value) return
  if (!['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) return
  pickerRef.value?.onKeydown(event)
  // Keep Enter from sending while the slash/zap picker is open.
  event.preventDefault()
  event.stopPropagation()
}

async function onHandoffResumed() {
  if (desk.profile.value) await desk.openProfile(desk.profile.value)
  await desk.refresh()
}

async function openCatalog() {
  catalogOpen.value = true
  catalogQuery.value = ''
  catalogError.value = ''
  catalogLoading.value = true
  try {
    catalogItems.value = await listCatalogItems()
  } catch (caught) {
    catalogError.value = userFacingError(caught, 'Could not load catalog products.')
    toast.error(catalogError.value)
  } finally {
    catalogLoading.value = false
  }
}

const catalogWindowOpen = computed(() => windowState.value?.status === 'open')

function catalogIdInvalid(item: any) {
  if (!item || !Object.prototype.hasOwnProperty.call(item, 'meta_catalog_id')) return false
  return !/^\d+$/.test(String(item.meta_catalog_id || '').trim())
}

const catalogSetupError = computed(() => {
  const invalid = catalogItems.value.filter((item) => catalogIdInvalid(item))
  if (!invalid.length) return ''
  const names = [...new Set(invalid.map((item) => item.catalog_name || item.catalog || 'Catalog'))]
  const found = String(invalid[0].meta_catalog_id || '').trim() || 'empty'
  return `Catalog ${names.join(', ')} cannot send any product. Meta Catalog ID must be digits only (found: ${found}). Set the numeric id from Meta Commerce Manager under Catalogs.`
})

function catalogItemBlocked(item: any) {
  return !catalogWindowOpen.value || catalogIdInvalid(item)
}

const filteredCatalogItems = computed(() => {
  const account = currentAccount.value || current.value?.profile?.whatsapp_account
  let rows = catalogItems.value
  if (account) {
    rows = rows.filter((item) => !item.whatsapp_account || item.whatsapp_account === account)
  }
  if (!catalogQuery.value.trim()) return rows
  const term = catalogQuery.value.toLowerCase()
  return rows.filter(
    (i) => (i.item_name || '').toLowerCase().includes(term) || (i.sku || '').toLowerCase().includes(term),
  )
})

async function sendProduct(item: any) {
  catalogError.value = ''
  if (!catalogWindowOpen.value) {
    catalogError.value =
      'Catalog send is blocked for every product. This chat has no incoming customer message in the last 24 hours, so the window is closed. Messages you send, including photos, do not open it. Ask the customer to reply, or send an approved template first.'
    toast.error(catalogError.value)
    return
  }
  if (catalogIdInvalid(item)) {
    catalogError.value = catalogSetupError.value || 'This catalog has no numeric Meta Catalog ID, so none of its products can be sent.'
    toast.error(catalogError.value)
    return
  }
  if (!desk.profile.value) {
    catalogError.value = 'Open a conversation before sending a catalog product.'
    toast.error(catalogError.value)
    return
  }
  catalogSending.value = true
  catalogSendingItem.value = item.name
  try {
    await sendCatalogProduct({
      profile: desk.profile.value,
      item: item.name,
    })
    toast.success(`Sent ${item.item_name}`)
    catalogOpen.value = false
    await desk.openProfile(desk.profile.value)
  } catch (caught) {
    catalogError.value = userFacingError(caught, 'Could not send this product.')
    toast.error(catalogError.value)
  } finally {
    catalogSending.value = false
    catalogSendingItem.value = ''
  }
}

async function assignToMe() {
  if (!desk.profile.value || !sessionUser) return
  try {
    await assignConversation(desk.profile.value, sessionUser)
    toast.success(`Assigned to ${sessionUser}`)
    await desk.refresh()
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

async function assignToUser() {
  if (!desk.profile.value || !assignUser.value) return
  try {
    await assignConversation(desk.profile.value, assignUser.value)
    toast.success('Assigned')
    assignUser.value = ''
    await desk.refresh()
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

async function clearAssignment(user?: string) {
  if (!desk.profile.value) return
  try {
    await unassignConversation(desk.profile.value, user)
    toast.success(user ? 'Removed assignment' : 'Unassigned')
    await desk.refresh()
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

function agentLabel(user?: string | null) {
  if (!user) return 'Unassigned'
  const known = filterUsers.value.find((row) => row.value === user)
  if (known?.label) return known.label
  return userLabel(user)
}

const headerAssignees = computed(() => assigneesOf({ assignment: currentAssignment.value }))

function assigneeSummary(people: string[]) {
  if (!people.length) return 'Unassigned'
  if (people.length === 1) return agentLabel(people[0])
  return `${agentLabel(people[0])} +${people.length - 1}`
}

const chatMatches = computed(() => {
  const term = chatQuery.value.trim().toLowerCase()
  if (!term) return []
  return composer.messages.filter((message) =>
    `${message.message || ''} ${message.template || ''} ${message.file_name || ''}`.toLowerCase().includes(term),
  )
})

function showMatch(index: number) {
  const rows = chatMatches.value
  if (!rows.length) return
  const next = ((index % rows.length) + rows.length) % rows.length
  matchCursor.value = next
  const el = document.getElementById(rows[next]!.name)
  el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  el?.classList.add('ring-2', 'ring-green-600')
  window.setTimeout(() => el?.classList.remove('ring-2', 'ring-green-600'), 1400)
}

function toggleChatSearch() {
  chatSearchOpen.value = !chatSearchOpen.value
  if (!chatSearchOpen.value) chatQuery.value = ''
}

function isCompact() {
  return window.matchMedia('(max-width: 1279px)').matches
}

function openContact() {
  if (isCompact()) {
    details.value = true
    return
  }
  contactOpen.value = true
}

function openAssign() {
  if (isCompact()) {
    details.value = true
    void nextTick(() => drawerProfile.value?.openAssign())
    return
  }
  contactOpen.value = true
  void nextTick(() => desktopProfile.value?.openAssign())
}

async function retryMessage(message: WhatsAppMessage) {
  if (message.media_url) {
    await desk.sendMedia(
      { file_url: message.media_url, file_name: message.file_name },
      message.mime_type || 'application/octet-stream',
      message.message || '',
    )
    return
  }
  if (message.is_template && message.whatsapp_template) {
    const template = (desk.inbox.value?.templates || []).find((row) => row.name === message.whatsapp_template)
    if (template) {
      await desk.sendTemplate(template)
      return
    }
  }
  const text = (message.message || message.template || '').trim()
  if (text) await desk.sendText(text)
}
</script>

<template>
  <div class="flex h-full min-w-0 overflow-hidden bg-wa-panel">
    <!-- Left Conversation Sidebar -->
    <aside
      class="inbox-list min-h-0 flex-col border-r border-wa bg-white"
      :class="desk.profile.value ? 'hidden md:flex' : 'flex'"
    >
      <div class="flex items-center justify-between gap-2 border-b border-wa px-3 py-2.5">
        <span class="text-base font-semibold text-wa-ink">Chats</span>
        <button
          v-if="canCreateProfile"
          type="button"
          class="grid size-9 place-items-center rounded-full bg-wa-accent text-white shadow-sm hover:opacity-90"
          title="New chat"
          aria-label="New chat"
          @click="openNewProfile"
        >
          <span class="lucide-plus size-5" aria-hidden="true" />
        </button>
      </div>

      <!-- Search & Filters Container -->
      <div class="border-b border-outline-gray-2 p-3 space-y-2.5 shrink-0 bg-white">
        <!-- Search Input with clear button -->
        <div class="relative">
          <TextInput
            v-model="query"
            placeholder="Search name or phone"
            class="w-full"
          />
          <button
            v-if="query"
            type="button"
            class="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-ink-gray-4 hover:bg-surface-gray-2 hover:text-ink-gray-7"
            title="Clear search"
            @click="query = ''"
          >
            <span class="lucide-x size-3" aria-hidden="true" />
          </button>
        </div>

        <div class="grid grid-cols-2 gap-2 pt-0.5">
          <Select
            class="w-full text-xs"
            :model-value="filter"
            :options="filterOptions"
            @update:model-value="(value) => { filter = (String(value || 'all') as typeof filter) }"
          />
          <Select
            class="w-full text-xs"
            :model-value="assignFilter"
            :options="assignOptions"
            @update:model-value="(value) => { assignFilter = String(value || 'all') }"
          />
        </div>
      </div>

      <ConversationList
        :conversations="conversations"
        :selected="desk.profile.value"
        :has-more="desk.inbox.value?.has_more"
        :row-status="rowStatus"
        :unread-count="unreadCount"
        :assignees-of="assigneesOf"
        :agent-label="agentLabel"
        @select="open"
        @clear-filters="clearSearch"
        @load-more="desk.loadMoreConversations()"
      />
    </aside>

    <!-- Center Chat Pane -->
    <section
      class="inbox-chat min-h-0 flex-row overflow-hidden bg-white"
      :class="desk.profile.value ? 'flex' : 'hidden md:flex'"
    >
      <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-wa-chat">
      <!-- Empty Canvas (No Conversation Selected) -->
      <div
        v-if="!current && !desk.threadLoading.value"
        class="grid flex-1 place-items-center bg-surface-gray-1 p-6 text-center"
      >
        <div class="max-w-md space-y-4">
          <div class="mx-auto grid size-16 place-items-center rounded-2xl bg-wa-teal/10 text-wa-teal shadow-xs">
            <span class="lucide-message-square size-8" aria-hidden="true" />
          </div>
          <div>
            <h3 class="text-lg font-bold tracking-tight text-ink-gray-9">Nudg Omnichannel Chat</h3>
            <p class="mt-1.5 text-xs leading-relaxed text-ink-gray-6">
              Select a customer conversation from the list to view complete message history, reply within the 24-hour SLA window, or send approved Meta templates.
            </p>
          </div>
          <div class="grid grid-cols-1 gap-3 pt-3 text-left sm:grid-cols-2">
            <div class="rounded-xl border border-outline-gray-2 bg-white p-3.5 shadow-xs">
              <p class="text-xs font-semibold text-ink-gray-9 flex items-center gap-1.5">
                <span class="lucide-clock size-3.5 text-emerald-600" /> 24h Service Window
              </p>
              <p class="mt-1 text-[11px] leading-relaxed text-ink-gray-5">
                Free-form text and attachments are permitted within 24h of customer messages.
              </p>
            </div>
            <div class="rounded-xl border border-outline-gray-2 bg-white p-3.5 shadow-xs">
              <p class="text-xs font-semibold text-ink-gray-9 flex items-center gap-1.5">
                <span class="lucide-layout-template size-3.5 text-wa-teal" /> Meta Templates
              </p>
              <p class="mt-1 text-[11px] leading-relaxed text-ink-gray-5">
                Initiate outbound threads or re-open conversations with approved templates.
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- Loading State -->
      <div v-else-if="!current && desk.threadLoading.value" class="grid flex-1 place-items-center text-sm text-ink-gray-6">
        <div class="flex items-center gap-2">
          <span class="lucide-loader-2 size-4 animate-spin text-wa-teal" />
          <span>Opening conversation thread…</span>
        </div>
      </div>

      <!-- Active Thread View -->
      <template v-else-if="current">
        <ChatHeader
          :profile="current.profile"
          :window-state="windowState"
          :now="now"
          :mode="desk.mode.value"
          :header-assignees="headerAssignees"
          :notes-count="notes.length"
          :notes-open="notesOpen"
          :chat-search-open="chatSearchOpen"
          :assignee-summary="assigneeSummary"
          :agent-label="agentLabel"
          @back="desk.openProfile(null)"
          @open-contact="openContact"
          @open-assign="openAssign"
          @assign-to-me="assignToMe"
          @clear-assignment="clearAssignment()"
          @toggle-notes="notesOpen = !notesOpen"
          @toggle-search="toggleChatSearch"
          @simulate-reply="desk.simulateReply()"
        />

        <div v-if="chatSearchOpen" class="flex shrink-0 items-center gap-2 border-b border-wa bg-white px-3 py-2">
          <TextInput v-model="chatQuery" class="min-w-0 flex-1" placeholder="Search in this conversation" />
          <span class="shrink-0 text-[11px] text-wa-subtle">
            {{ chatQuery.trim() ? `${chatMatches.length ? matchCursor + 1 : 0}/${chatMatches.length}` : '' }}
          </span>
          <button type="button" class="grid size-7 place-items-center rounded-full text-wa-muted hover:bg-wa-panel" title="Previous match" @click="showMatch(matchCursor - 1)">
            <span class="lucide-chevron-up size-4" aria-hidden="true" />
          </button>
          <button type="button" class="grid size-7 place-items-center rounded-full text-wa-muted hover:bg-wa-panel" title="Next match" @click="showMatch(matchCursor + 1)">
            <span class="lucide-chevron-down size-4" aria-hidden="true" />
          </button>
        </div>

        <div
          v-if="presenceLabel"
          class="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-900"
        >
          {{ presenceLabel }}
        </div>

        <BotHandoffBanner
          :bot-status="current.bot_status"
          :account="current.profile.whatsapp_account"
          @resumed="onHandoffResumed"
        />

        <div v-if="notesOpen" class="border-b border-outline-gray-2 bg-amber-50/70 px-4 py-3">
          <p class="text-xs text-ink-gray-6">Internal notes stay on this conversation. They are never sent on WhatsApp.</p>
          <ul v-if="notes.length" class="mt-2 max-h-36 space-y-2 overflow-y-auto">
            <li v-for="note in notes" :key="note.name" class="rounded-md bg-white px-3 py-2 text-xs">
              <div class="font-semibold text-ink-gray-8">{{ note.author || 'Agent' }}</div>
              <div class="mt-0.5 whitespace-pre-wrap text-ink-gray-7">{{ note.content }}</div>
            </li>
          </ul>
          <form class="mt-2 flex flex-wrap items-center gap-2" @submit.prevent="saveNote">
            <TextInput v-model="noteText" class="min-w-0 flex-1" placeholder="Add an internal note" />
            <Button type="submit" size="sm" variant="solid" loading-text="Saving…" label="Save" :loading="savingNote" :disabled="!noteText.trim()" />
          </form>
        </div>

        <!-- Message History Canvas -->
        <div
          ref="scroller"
          class="wa-chat-wallpaper min-h-0 min-w-0 flex-1 overflow-y-auto px-3 py-3 sm:px-6 md:px-10"
          @scroll="onChatScroll"
          @load.capture="scrollToLatest"
        >
          <button
            v-if="current?.has_older"
            type="button"
            class="mb-3 w-full rounded-md bg-white/80 px-3 py-2 text-center text-xs font-semibold text-wa-teal shadow-sm"
            @click="loadEarlier"
          >
            Load earlier messages
          </button>
          <MessageList
            :key="current.profile.name"
            :messages="composer.messages"
            :loading="desk.threadLoading.value"
            :sender-name="current.profile.profile_name"
            @reply="composer.setReplyTo"
            @react="onReact"
            @retry="retryMessage"
          />
        </div>

        <!-- Blocked Profile Notification -->
        <div
          v-if="current.profile.status === 'Blocked'"
          class="border-t border-red-200 bg-red-50 px-4 py-3 text-xs text-red-800 shrink-0"
        >
          <div class="flex items-center gap-2">
            <span class="lucide-ban size-4 text-red-600 shrink-0" aria-hidden="true" />
            <span>This customer profile is marked as <strong>Blocked</strong>. Unblock on the WhatsApp Profile record to allow outgoing messaging.</span>
          </div>
        </div>

        <!-- 24h Window Closed Helper Callout Banner -->
        <div
          v-else-if="windowState?.status !== 'open'"
          class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 border-t border-amber-200 bg-gradient-to-r from-amber-50 to-orange-50/50 px-4 py-2.5 text-xs text-amber-900 shrink-0"
        >
          <div class="flex items-center gap-2 min-w-0">
            <span class="lucide-clock-alert size-4 text-amber-600 shrink-0" aria-hidden="true" />
            <span class="truncate">
              <strong>24-Hour Window Closed.</strong> Meta allows only approved WhatsApp Templates outside the 24h window.
            </span>
          </div>
          <Button size="sm" variant="solid" theme="green" label="Select Template to Send" icon-left="lucide-layout-template" @click="templateOpen = true" class="w-full sm:w-auto shrink-0"/>
        </div>

        <!-- Message Composer Input -->
        <div
          v-if="current.profile.status !== 'Blocked'"
          ref="composerRoot"
          class="inbox-composer relative sticky bottom-0 z-10 shrink-0 border-t border-wa bg-wa-panel px-2 py-2 sm:px-3"
          @keydown.capture="onComposerKeydown"
        >
          <CannedReplyPicker
            ref="pickerRef"
            :open="pickerOpen"
            :query="pickerFilter"
            :replies="quickReplies"
            :loading="quickLoading"
            @select="onPickReply"
            @close="closePicker"
            @update:query="onPickerQuery"
          />
          <MessageInput
            v-bind="composer"
            :sender-name="current.profile.profile_name"
            placeholder="Type a message… (/ for quick replies)"
            window-closed-label=""
            window-unopened-label=""
          >
            <template #leading-actions>
              <button
                type="button"
                class="grid size-10 place-items-center rounded-full text-wa-muted hover:bg-black/5"
                :class="pickerOpen ? 'bg-surface-gray-2 text-ink-gray-9' : ''"
                :title="pickerOpen ? 'Close quick replies' : 'Quick replies (/)'"
                :aria-label="pickerOpen ? 'Close quick replies' : 'Quick replies'"
                :aria-expanded="pickerOpen"
                @click="toggleQuickReplies"
              >
                <span class="lucide-zap size-5" aria-hidden="true" />
              </button>
              <button
                type="button"
                class="hidden size-10 place-items-center rounded-full text-wa-muted hover:bg-black/5 sm:grid"
                title="Send template"
                @click="templateOpen = true"
              >
                <span class="lucide-layout-template size-5" aria-hidden="true" />
              </button>
              <button
                type="button"
                class="hidden size-10 place-items-center rounded-full text-wa-muted hover:bg-black/5 sm:grid"
                title="Catalog"
                @click="openCatalog"
              >
                <span class="lucide-shopping-bag size-5" aria-hidden="true" />
              </button>
            </template>
          </MessageInput>
        </div>
      </template>
      </div>

      <aside
        v-if="current && contactOpen"
        class="inbox-rail inbox-rail-open relative hidden h-auto min-h-0 flex-col self-stretch border-l border-wa bg-white xl:flex"
      >
        <div class="flex h-14 shrink-0 items-center gap-2 border-b border-wa px-2">
          <button
            type="button"
            class="grid size-8 shrink-0 place-items-center rounded-full text-wa-muted hover:bg-wa-panel"
            title="Collapse contact info"
            aria-label="Collapse contact info"
            @click="contactOpen = false"
          >
            <span class="lucide-panel-right-close size-4" aria-hidden="true" />
          </button>
          <span class="truncate text-sm font-semibold text-wa-ink">Contact info</span>
        </div>
        <ProfileDetails
          ref="desktopProfile"
          class="min-h-0 flex-1 overflow-y-auto"
          :thread="current"
          :assignment="currentAssignment"
          @assign="(user) => { assignUser = user; assignToUser(); }"
          @unassign="(user: string) => clearAssignment(user)"
        />
      </aside>
    </section>

    <div v-if="details && current" class="fixed inset-0 z-50 xl:hidden">
      <button type="button" class="absolute inset-0 bg-black/40" aria-label="Close contact info" @click="details = false" />
      <aside class="absolute inset-x-0 bottom-0 flex max-h-[min(70dvh,32rem)] w-full flex-col overflow-hidden rounded-t-2xl bg-white pb-[env(safe-area-inset-bottom)] shadow-xl">
        <div class="flex h-11 shrink-0 items-center justify-between border-b border-wa px-3">
          <span class="text-sm font-semibold text-wa-ink">Contact info</span>
          <button type="button" class="grid size-8 place-items-center rounded-full text-wa-muted hover:bg-wa-panel" aria-label="Close" @click="details = false">
            <span class="lucide-x size-4" aria-hidden="true" />
          </button>
        </div>
        <ProfileDetails
          ref="drawerProfile"
          class="min-h-0 overflow-y-auto"
          :thread="current"
          :assignment="currentAssignment"
          @assign="(user) => { assignUser = user; assignToUser(); }"
          @unassign="(user: string) => clearAssignment(user)"
        />
      </aside>
    </div>

    <!-- Send WhatsApp Template Modal Dialog (2-Column Studio Preview) -->
    <Dialog v-model="templateOpen" size="7xl" title="Send WhatsApp Template">
      <div class="space-y-3">
        <!-- Search & Filter Controls -->
        <div class="flex flex-col sm:flex-row gap-2">
          <TextInput
            v-model="templateQuery"
            placeholder="Search templates by name, label, or body…"
            class="flex-1"
          />
          <div class="flex items-center gap-1">
            <Button
              size="sm"
              label="All"
              :variant="templateTypeFilter === 'all' ? 'solid' : 'subtle'"
              :theme="templateTypeFilter === 'all' ? 'green' : 'gray'"
              :data-state="templateTypeFilter === 'all' ? 'active' : undefined"
              :aria-pressed="templateTypeFilter === 'all'"
              @click="templateTypeFilter = 'all'"
            />
            <Button
              size="sm"
              label="Utility"
              :variant="templateTypeFilter === 'Utility' ? 'solid' : 'subtle'"
              :theme="templateTypeFilter === 'Utility' ? 'green' : 'gray'"
              :data-state="templateTypeFilter === 'Utility' ? 'active' : undefined"
              :aria-pressed="templateTypeFilter === 'Utility'"
              @click="templateTypeFilter = 'Utility'"
            />
            <Button
              size="sm"
              label="Marketing"
              :variant="templateTypeFilter === 'Marketing' ? 'solid' : 'subtle'"
              :theme="templateTypeFilter === 'Marketing' ? 'green' : 'gray'"
              :data-state="templateTypeFilter === 'Marketing' ? 'active' : undefined"
              :aria-pressed="templateTypeFilter === 'Marketing'"
              @click="templateTypeFilter = 'Marketing'"
            />
          </div>
        </div>

        <!-- Two Column Picker & Live Preview -->
        <div class="grid max-h-[50vh] min-h-0 grid-cols-1 gap-4 md:h-[min(68vh,40rem)] md:max-h-none md:min-h-[24rem] md:grid-cols-2">
          <!-- Template Selection List -->
          <div class="min-h-0 space-y-2 overflow-y-auto pr-1">
            <p v-if="filteredTemplates.length === 0" class="py-8 text-center text-xs text-ink-gray-5">
              No matching templates found.
            </p>
            <button
              v-for="template in filteredTemplates"
              :key="template.name"
              type="button"
              class="flex flex-col w-full rounded-xl border p-3 text-left transition-all"
              :class="
                picked?.name === template.name
                  ? 'border-[var(--wa-teal-deep)] bg-teal-50/60 shadow-xs ring-1 ring-[var(--wa-teal-deep)]'
                  : 'border-outline-gray-2 hover:border-outline-gray-4 hover:bg-surface-gray-1'
              "
              @click="chooseTemplate(template)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-semibold text-ink-gray-9">
                  {{ displayTitle(template.template_label, template.template_name) || 'Untitled template' }}
                </span>
                <StatusBadge :label="template.status || 'Pending'" />
              </div>
              <p class="mt-1 line-clamp-2 text-xs text-ink-gray-6">{{ template.message }}</p>
              <div class="mt-2 flex items-center gap-2 text-[10px] text-ink-gray-5">
                <span class="font-medium text-wa-teal">{{ template.template_type }}</span>
                <span>·</span>
                <span>{{ template.language }}</span>
                <span v-if="template.buttons?.length">· {{ template.buttons.length }} buttons</span>
              </div>
            </button>
          </div>

          <!-- Live WhatsApp Bubble Preview -->
          <div class="flex min-h-0 flex-col overflow-y-auto rounded-xl border border-outline-gray-2 bg-wa-chat/40 p-4">
            <p class="pb-3 text-[11px] font-bold uppercase tracking-wider text-ink-gray-5">Live Template Preview</p>
            <div v-if="picked" class="flex flex-1 flex-col justify-center">
              <DeskTemplatePreview :template="picked" mode="preview" :editable="false" large />
            </div>
            <div v-else class="flex-1 grid place-items-center text-center text-xs text-ink-gray-5 p-6">
              Select a template from the list on the left to preview its formatted layout and action buttons.
            </div>
          </div>
        </div>
      </div>

      <template #actions>
        <div class="flex w-full flex-wrap items-center justify-between gap-2">
          <span v-if="picked" class="text-xs text-ink-gray-6 truncate max-w-xs">
            Selected: <strong>{{ displayTitle(picked.template_label, picked.template_name) || 'Untitled template' }}</strong>
          </span>
          <span v-else />
          <div class="flex gap-2">
            <Button label="Cancel" @click="templateOpen = false" />
            <Button variant="solid" theme="green" label="Send Template" icon-left="lucide-send" loading-text="Sending…" :disabled="!picked" :loading="desk.sending.value" @click="sendPicked"/>
          </div>
        </div>
      </template>
    </Dialog>

    <!-- Send Catalog Product Modal Dialog -->
    <Dialog v-model="catalogOpen" title="Send Catalog Product">
      <div class="space-y-3">
        <div
          v-if="!catalogWindowOpen"
          class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"
        >
          <strong>Catalog send blocked: 24-hour window is closed.</strong>
          This chat has no incoming customer message in the last 24 hours.
          Photos and texts sent from this desk do not open the window.
          Ask the customer to reply, or send an approved template first.
          Every Send Product button is disabled for that same reason.
        </div>
        <div
          v-if="catalogSetupError"
          class="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800"
        >
          {{ catalogSetupError }}
        </div>
        <div
          v-if="catalogError"
          class="whitespace-pre-wrap rounded-xl border border-red-300 bg-red-50 p-3 text-xs text-red-900"
        >
          <strong>Send failed.</strong>
          {{ catalogError }}
        </div>

        <TextInput
          v-model="catalogQuery"
          placeholder="Search items by product name or SKU…"
          class="w-full"
        />

        <div v-if="catalogLoading" class="py-8 text-center text-xs text-ink-gray-5">
          <span class="lucide-loader-2 size-4 animate-spin text-wa-teal" />
          <p class="mt-2">Loading catalog items…</p>
        </div>
        <div v-else-if="!filteredCatalogItems.length" class="py-8 text-center text-xs text-ink-gray-5">
          No catalog items found. Manage products under <strong>Catalogs</strong>.
        </div>
        <div v-else class="grid max-h-96 gap-2.5 overflow-y-auto">
          <div
            v-for="item in filteredCatalogItems"
            :key="item.name"
            class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-white p-3 transition-colors hover:border-outline-gray-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div class="flex items-center gap-3 min-w-0">
              <div class="size-11 shrink-0 rounded-lg border border-outline-gray-2 bg-surface-gray-1 flex items-center justify-center overflow-hidden text-base">
                <img v-if="item.image" :src="item.image" class="size-full object-cover" :alt="item.item_name" />
                <span v-else>🛍️</span>
              </div>
              <div class="min-w-0">
                <div class="truncate text-sm font-semibold text-ink-gray-9">{{ item.item_name }}</div>
                <div class="flex items-center gap-2 text-xs text-ink-gray-5 mt-0.5">
                  <span class="font-mono text-emerald-700 font-semibold">{{ item.currency || 'USD' }} {{ item.price }}</span>
                  <span v-if="item.sku" class="truncate font-mono">SKU: {{ item.sku }}</span>
                </div>
              </div>
            </div>
            <Button
              size="sm"
              :variant="catalogItemBlocked(item) ? 'subtle' : 'solid'"
              :theme="catalogItemBlocked(item) ? 'gray' : 'green'"
              label="Send Product"
              icon-left="lucide-send"
              loading-text="Sending…"
              :loading="catalogSending && catalogSendingItem === item.name"
              class="w-full sm:w-auto"
              :disabled="!catalogWindowOpen || catalogIdInvalid(item) || catalogSending"
              @click="sendProduct(item)"
            />
          </div>
        </div>
      </div>
      <template #actions>
        <Button label="Close" @click="catalogOpen = false" />
      </template>
    </Dialog>

    <Dialog v-model="newProfileOpen" title="New chat">
      <div class="grid gap-3">
        <p class="text-sm text-ink-gray-7">
          Create a contact and open the conversation. If this number already exists, that chat opens instead.
        </p>
        <FormControl v-model="newProfile.profile_name" type="text" label="Name" placeholder="Contact name" />
        <FormControl v-model="newProfile.phone_number" type="text" label="Phone number" placeholder="+91…" />
        <p class="text-xs text-ink-gray-5">
          WhatsApp account: {{ currentAccountLabel || 'Select a number in the top bar' }}
        </p>
      </div>
      <template #actions>
        <Button label="Cancel" @click="newProfileOpen = false" />
        <Button variant="solid" theme="green" loading-text="Creating…" label="Create" :loading="newProfileSaving" @click="createProfileFromChat"/>
      </template>
    </Dialog>
  </div>
</template>
