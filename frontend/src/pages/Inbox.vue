<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Avatar, Button, Dialog, Dropdown, Select, TextInput, call, toast } from 'frappe-ui'
import { MessageInput, MessageList } from '@whatsapp/ui/components/Messages'
import type { ReactPayload, WhatsAppMessage } from '@whatsapp/ui/components/Messages'
import DeskTemplatePreview from '@/components/DeskTemplatePreview.vue'
import ProfileDetails from '@/components/ProfileDetails.vue'
import {
  CONVERSATION_STATUS_FILTERS,
  CONVERSATION_STATUS_LABEL,
  conversationStatusAt,
  conversationStatusOf,
} from '@/utils/conversationStatus'
import { useDeskComposer } from '@/composables/useComposer'
import { formatDay, formatRemaining, formatTime, initials, previewText, serviceWindow } from '@/utils/format'
import { userFacingError } from '@/utils/errors'
import { useDesk } from '@/stores/desk'
import {
  assignConversation,
  listCatalogItems,
  listQuickReplies,
  sendCatalogProduct,
  unassignConversation,
  useQuickReply,
} from '@/services/catalogApi'
import { errorText } from '@/utils/format'
import { threadAccountAllowed } from '@/utils/deskCache'
import type { Conversation, ConversationNote, Template } from '@/types'

const desk = useDesk()
const route = useRoute()
const composer = useDeskComposer()
const query = ref('')
const filter = ref<'all' | ReturnType<typeof conversationStatusOf>>('all')
const assignFilter = ref<'all' | 'mine' | 'unassigned'>('all')
const quickTab = ref<'all' | 'needs_reply' | 'window_open' | 'unassigned'>('all')

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

const quickOpen = ref(false)
const quickQuery = ref('')
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
const quickReplies = ref<any[]>([])

const catalogOpen = ref(false)
const catalogQuery = ref('')
const catalogLoading = ref(false)
const catalogSending = ref(false)
const catalogSendingItem = ref('')
const catalogError = ref('')
const catalogItems = ref<any[]>([])

const assignUser = ref('')
const picked = ref<Template | null>(null)
const scroller = ref<HTMLElement | null>(null)
const sessionUser = window.user || ''
const now = ref(Date.now())
let clock = 0
onMounted(() => {
  clock = window.setInterval(() => {
    now.value = Date.now()
  }, 30000)
})
onUnmounted(() => window.clearInterval(clock))

function rowStatus(row: Conversation) {
  return conversationStatusAt(row, now.value)
}

const filterOptions = CONVERSATION_STATUS_FILTERS.map((row) => ({
  label: row.label,
  value: row.value,
}))

// Synchronize quickTab with filter and assignFilter
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
  quickTab.value = tab
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

// Live counts for quick chips
const allRows = computed(() => {
  const rows = desk.inbox.value?.conversations || []
  const selected = desk.account.value
  if (!selected || selected === 'all') return rows
  return rows.filter((row) => row.profile.whatsapp_account === selected)
})
const countAll = computed(() => allRows.value.length)
const countNeedsReply = computed(
  () => allRows.value.filter((r) => rowStatus(r) === 'needs_reply').length,
)
const countWindowOpen = computed(
  () => allRows.value.filter((r) => rowStatus(r) === 'window_open').length,
)
const countUnassigned = computed(
  () => allRows.value.filter((r) => !r.assignment?.assignee || r.assignment?.assignment_status === 'Unassigned').length,
)

const conversations = computed(() => {
  const rows = allRows.value
  return rows.filter((row) => {
    const haystack = `${row.profile.profile_name} ${row.profile.phone_number} ${previewText(row.preview)}`.toLowerCase()
    if (query.value && !haystack.includes(query.value.toLowerCase())) return false
    if (assignFilter.value === 'mine' && row.assignment?.assignee !== sessionUser) return false
    if (assignFilter.value === 'unassigned' && row.assignment?.assignee && row.assignment?.assignment_status !== 'Unassigned') return false
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

watch(
  () => [desk.profile.value, current.value?.messages.length] as const,
  async () => {
    await nextTick()
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  },
)

function open(row: Conversation) {
  void desk.openProfile(row.profile.name)
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
  const list = desk.inbox.value?.templates || []
  return list.filter((t) => {
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

async function openQuickReplies() {
  quickQuery.value = ''
  try {
    quickReplies.value = await listQuickReplies(desk.account.value === 'all' ? undefined : desk.account.value)
    quickOpen.value = true
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

const filteredQuickReplies = computed(() => {
  if (!quickQuery.value.trim()) return quickReplies.value
  const term = quickQuery.value.toLowerCase()
  return quickReplies.value.filter(
    (q) => (q.title || '').toLowerCase().includes(term) || (q.body || '').toLowerCase().includes(term),
  )
})

async function insertQuickReply(name: string) {
  try {
    const reply = await useQuickReply(name)
    composer.setDraft(reply.body)
    quickOpen.value = false
  } catch (caught) {
    toast.error(errorText(caught))
  }
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
  return `Catalog ${names.join(', ')} cannot send any product. Meta Catalog ID must be digits only (found: ${found}). Set the numeric id from Meta Commerce Manager under Integrations → Catalogs.`
})

function catalogItemBlocked(item: any) {
  return !catalogWindowOpen.value || catalogIdInvalid(item)
}

const filteredCatalogItems = computed(() => {
  if (!catalogQuery.value.trim()) return catalogItems.value
  const term = catalogQuery.value.toLowerCase()
  return catalogItems.value.filter(
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

async function clearAssignment() {
  if (!desk.profile.value) return
  try {
    await unassignConversation(desk.profile.value)
    toast.success('Unassigned')
    await desk.refresh()
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

function agentLabel(user?: string | null) {
  if (!user) return 'Unassigned'
  const local = user.split('@')[0] || user
  return local.replace(/[._]/g, ' ')
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
  el?.classList.add('ring-2', 'ring-[#00A884]')
  window.setTimeout(() => el?.classList.remove('ring-2', 'ring-[#00A884]'), 1400)
}

function toggleChatSearch() {
  chatSearchOpen.value = !chatSearchOpen.value
  if (!chatSearchOpen.value) chatQuery.value = ''
}

function isPhone() {
  return window.matchMedia('(max-width: 767px)').matches
}

function openContact() {
  if (isPhone()) {
    details.value = true
    return
  }
  contactOpen.value = true
}

function openAssign() {
  if (isPhone()) {
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
  <div class="flex h-full min-w-0 overflow-hidden bg-[#F0F2F5]">
    <!-- Left Conversation Sidebar -->
    <aside
      class="inbox-list flex min-h-0 flex-col border-r border-[#E9EDEF] bg-white"
      :class="desk.profile.value ? 'hidden md:flex' : 'flex'"
    >
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

        <!-- Quick Filter Pills -->
        <div class="flex flex-wrap items-center gap-1.5 pb-1 text-xs">
          <button
            type="button"
            class="inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 font-medium transition-colors"
            :class="quickTab === 'all' ? 'bg-[#075E54] text-white shadow-xs' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3 hover:text-ink-gray-9'"
            @click="selectQuickTab('all')"
          >
            <span>All</span>
            <span class="rounded-full px-1.5 py-0.2 text-[10px] font-bold" :class="quickTab === 'all' ? 'bg-white/25 text-white' : 'bg-black/10 text-ink-gray-7'">{{ countAll }}</span>
          </button>

          <button
            type="button"
            class="inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 font-medium transition-colors"
            :class="quickTab === 'needs_reply' ? 'bg-red-600 text-white shadow-xs' : 'bg-red-50 text-red-700 hover:bg-red-100'"
            @click="selectQuickTab('needs_reply')"
          >
            <span>Needs Reply</span>
            <span
              v-if="countNeedsReply > 0"
              class="rounded-full px-1.5 py-0.2 text-[10px] font-bold"
              :class="quickTab === 'needs_reply' ? 'bg-white/25 text-white' : 'bg-red-200 text-red-800'"
            >
              {{ countNeedsReply }}
            </span>
          </button>

          <button
            type="button"
            class="inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 font-medium transition-colors"
            :class="quickTab === 'window_open' ? 'bg-[#075E54] text-white shadow-xs' : 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'"
            @click="selectQuickTab('window_open')"
          >
            <span class="size-1.5 rounded-full" :class="quickTab === 'window_open' ? 'bg-white' : 'bg-emerald-600'" />
            <span>Open 24h</span>
            <span
              class="rounded-full px-1.5 py-0.2 text-[10px] font-bold"
              :class="quickTab === 'window_open' ? 'bg-white/25 text-white' : 'bg-emerald-200 text-emerald-900'"
            >
              {{ countWindowOpen }}
            </span>
          </button>

          <button
            type="button"
            class="inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 font-medium transition-colors"
            :class="quickTab === 'unassigned' ? 'bg-blue-600 text-white shadow-xs' : 'bg-blue-50 text-blue-700 hover:bg-blue-100'"
            @click="selectQuickTab('unassigned')"
          >
            <span>Unassigned</span>
            <span
              class="rounded-full px-1.5 py-0.2 text-[10px] font-bold"
              :class="quickTab === 'unassigned' ? 'bg-white/25 text-white' : 'bg-blue-200 text-blue-800'"
            >
              {{ countUnassigned }}
            </span>
          </button>
        </div>

        <!-- Secondary Filter Controls -->
        <div class="grid grid-cols-2 gap-2 pt-0.5">
          <Select
            class="w-full text-xs"
            :model-value="filter"
            :options="filterOptions"
            @update:model-value="(value) => { filter = (String(value || 'all') as typeof filter); quickTab = 'all'; }"
          />
          <Select
            class="w-full text-xs"
            :model-value="assignFilter"
            :options="[
              { label: 'Anyone', value: 'all' },
              { label: 'Assigned to me', value: 'mine' },
              { label: 'Unassigned', value: 'unassigned' },
            ]"
            @update:model-value="(value) => { assignFilter = (String(value || 'all') as typeof assignFilter); quickTab = 'all'; }"
          />
        </div>
      </div>

      <!-- Conversation List Scroller -->
      <div class="min-h-0 flex-1 overflow-y-auto divide-y divide-outline-gray-1">
        <!-- Empty Results View -->
        <div v-if="conversations.length === 0" class="p-6 text-center text-xs text-ink-gray-5">
          <div class="mx-auto grid size-10 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-4">
            <span class="lucide-search-x size-5" aria-hidden="true" />
          </div>
          <p class="mt-2 font-medium text-ink-gray-8">No conversations found</p>
          <p class="mt-1 text-ink-gray-5">No threads match your current search or filter filters.</p>
          <button
            type="button"
            class="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-[#075E54] hover:underline"
            @click="clearSearch"
          >
            Clear all filters
          </button>
        </div>

        <!-- Conversation Item Cards -->
        <button
          v-for="row in conversations"
          :key="row.profile.name"
          type="button"
          class="flex w-full gap-3 px-3 py-3 text-left transition-all hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#128C7E]"
          :class="
            desk.profile.value === row.profile.name
              ? 'bg-teal-50/70 border-l-4 border-l-[#075E54]'
              : 'border-l-4 border-l-transparent'
          "
          @click="open(row)"
        >
          <!-- Avatar with window state dot -->
          <div class="shrink-0 self-start">
            <Avatar :label="row.profile.profile_name || row.profile.phone_number" size="xl">
              <template #indicator>
                <span
                  v-if="rowStatus(row) === 'window_open'"
                  class="size-2.5 rounded-full bg-[#25D366] ring-2 ring-white"
                  title="24h Service Window Open"
                />
                <span
                  v-else-if="row.needs_reply"
                  class="size-2.5 rounded-full bg-red-500 ring-2 ring-white"
                  title="Needs Reply"
                />
              </template>
            </Avatar>
          </div>

          <!-- Conversation Summary -->
          <div class="flex min-w-0 flex-1 items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <!-- Row 1: Name -->
              <span
                class="block text-sm font-semibold leading-snug"
                :class="desk.profile.value === row.profile.name ? 'text-[#075E54]' : 'text-ink-gray-9'"
              >
                {{ row.profile.profile_name || row.profile.phone_number }}
              </span>

              <!-- Row 2: Message Preview Snippet -->
              <p class="mt-0.5 truncate text-xs text-ink-gray-6">
                <span v-if="row.preview?.direction === 'Outgoing'" class="font-medium text-ink-gray-5">You: </span>
                <span>{{ previewText(row.preview) }}</span>
              </p>

              <!-- Row 3: Status Tags & Meta -->
              <div class="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px]">
                <!-- Needs Reply Badge -->
                <span
                  v-if="row.needs_reply"
                  class="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 font-semibold text-red-700 ring-1 ring-red-600/20"
                >
                  Needs reply
                </span>

                <!-- Window Open Remaining Time -->
                <span
                  v-else-if="rowStatus(row) === 'window_open'"
                  class="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700 ring-1 ring-emerald-600/20"
                >
                  <span class="size-1.5 rounded-full bg-emerald-500" />
                  {{ formatRemaining(row.window.expires_at, now) }}
                </span>

                <!-- Failed Pill -->
                <span
                  v-else-if="rowStatus(row) === 'failed'"
                  class="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 font-medium text-red-700"
                >
                  Failed
                </span>

                <!-- Blocked Pill -->
                <span
                  v-else-if="rowStatus(row) === 'blocked'"
                  class="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 font-medium text-gray-700"
                >
                  Blocked
                </span>

                <!-- Template Only -->
                <span
                  v-else-if="rowStatus(row) === 'template_only'"
                  class="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-700"
                >
                  Template only
                </span>
              </div>
            </div>

            <!-- Timestamp, with assignee initial under it -->
            <div class="flex shrink-0 flex-col items-end gap-1">
              <span class="text-[11px] text-ink-gray-5 font-mono">
                {{ row.preview?.creation ? formatTime(row.preview.creation) : '' }}
              </span>
              <Avatar
                v-if="row.assignment?.assignee && row.assignment.assignment_status !== 'Unassigned'"
                :label="row.assignment.assignee"
                size="sm"
                theme="blue"
                :title="row.assignment.assignee"
              />
            </div>
          </div>
        </button>
      </div>
    </aside>

    <!-- Center Chat Pane -->
    <section
      class="inbox-chat flex min-h-0 flex-row overflow-hidden bg-white"
      :class="desk.profile.value ? 'flex' : 'hidden md:flex'"
    >
      <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[#efeae2]">
      <!-- Empty Canvas (No Conversation Selected) -->
      <div
        v-if="!current && !desk.threadLoading.value"
        class="grid flex-1 place-items-center bg-surface-gray-1 p-6 text-center"
      >
        <div class="max-w-md space-y-4">
          <div class="mx-auto grid size-16 place-items-center rounded-2xl bg-[#075E54]/10 text-[#075E54] shadow-xs">
            <span class="lucide-message-square size-8" aria-hidden="true" />
          </div>
          <div>
            <h3 class="text-lg font-bold tracking-tight text-ink-gray-9">Nudg Omnichannel Chat</h3>
            <p class="mt-1.5 text-xs leading-relaxed text-ink-gray-6">
              Select a customer conversation from the list to view complete message history, reply within the 24-hour SLA window, or send approved Meta templates.
            </p>
          </div>
          <div class="grid grid-cols-2 gap-3 pt-3 text-left">
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
                <span class="lucide-layout-template size-3.5 text-[#075E54]" /> Meta Templates
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
          <span class="lucide-loader-2 size-4 animate-spin text-[#075E54]" />
          <span>Opening conversation thread…</span>
        </div>
      </div>

      <!-- Active Thread View -->
      <template v-else-if="current">
        <!-- Thread Header -->
        <header class="inbox-chat-header z-10 flex h-14 shrink-0 items-center gap-2 overflow-x-auto border-b border-[#E9EDEF] bg-white px-3">
          <div class="inbox-contact flex items-center gap-2.5">
            <button
              type="button"
              class="inline-flex size-9 items-center justify-center rounded-full text-[#54656F] hover:bg-[#F0F2F5] md:hidden"
              title="Back to conversation list"
              @click="desk.openProfile(null)"
            >
              <span class="lucide-arrow-left size-5" aria-hidden="true" />
            </button>

            <button
              type="button"
              class="flex items-center gap-2.5 rounded-lg text-left hover:bg-[#F0F2F5]"
              title="Contact info"
              @click="openContact"
            >
              <span class="relative shrink-0">
                <Avatar :label="current.profile.profile_name || current.profile.phone_number" size="lg" />
                <span
                  v-if="current.profile.status === 'Active'"
                  class="absolute bottom-0 right-0 size-2.5 rounded-full bg-[#25D366] ring-2 ring-white"
                />
              </span>
              <span>
                <span class="block whitespace-nowrap text-sm font-semibold leading-tight text-[#111B21]">
                  {{ current.profile.profile_name || current.profile.phone_number }}
                </span>
                <span class="block whitespace-nowrap text-xs leading-tight text-[#667781]">
                  {{ current.profile.phone_number }}
                </span>
              </span>
            </button>
          </div>

          <div class="flex shrink-0 items-center gap-1.5">
            <div
              v-if="windowState?.status === 'open'"
              class="hidden items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 sm:inline-flex"
              title="24-hour customer care window is open"
            >
              <span class="size-1.5 rounded-full bg-emerald-500" />
              <span>{{ formatRemaining(windowState.expires_at, now) }}</span>
            </div>
            <div
              v-else
              class="hidden items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 sm:inline-flex"
              title="24-hour window is closed. Send an approved template."
            >
              Window closed
            </div>

            <Button
              v-if="desk.mode.value === 'sample' && windowState?.status === 'closed'"
              size="sm"
              variant="subtle"
              label="Simulate reply"
              @click="desk.simulateReply()"
            />

            <Dropdown
              :options="[
                { label: 'Assign to me', onClick: assignToMe },
                { label: 'Reassign', onClick: openAssign },
                ...(currentAssignment?.assignee ? [{ label: 'Unassign', onClick: clearAssignment }] : []),
              ]"
            >
              <button
                type="button"
                class="hidden h-8 items-center gap-1.5 rounded-full border border-[#E9EDEF] bg-white px-2 text-xs font-medium text-[#111B21] hover:bg-[#F0F2F5] sm:inline-flex"
              >
                <Avatar :label="currentAssignment?.assignee || 'Unassigned'" size="sm" />
                <span class="whitespace-nowrap">{{ agentLabel(currentAssignment?.assignee) }}</span>
                <span class="lucide-chevron-down size-3 text-[#667781]" aria-hidden="true" />
              </button>
            </Dropdown>

            <button
              type="button"
              class="inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-xs font-medium text-[#54656F] hover:bg-[#F0F2F5]"
              :class="notesOpen ? 'bg-emerald-50 text-emerald-700' : ''"
              @click="notesOpen = !notesOpen"
            >
              <span class="lucide-sticky-note size-4" aria-hidden="true" />
              <span>Notes<span v-if="notes.length"> {{ notes.length }}</span></span>
            </button>

            <button
              type="button"
              class="grid size-8 place-items-center rounded-full text-[#54656F] hover:bg-[#F0F2F5]"
              :class="chatSearchOpen ? 'bg-[#F0F2F5] text-[#00A884]' : ''"
              title="Search in conversation"
              @click="toggleChatSearch"
            >
              <span class="lucide-search size-4" aria-hidden="true" />
            </button>

          </div>
        </header>

        <div v-if="chatSearchOpen" class="flex shrink-0 items-center gap-2 border-b border-[#E9EDEF] bg-white px-3 py-2">
          <TextInput v-model="chatQuery" class="min-w-0 flex-1" placeholder="Search in this conversation" />
          <span class="shrink-0 text-[11px] text-[#667781]">
            {{ chatQuery.trim() ? `${chatMatches.length ? matchCursor + 1 : 0}/${chatMatches.length}` : '' }}
          </span>
          <button type="button" class="grid size-7 place-items-center rounded-full text-[#54656F] hover:bg-[#F0F2F5]" title="Previous match" @click="showMatch(matchCursor - 1)">
            <span class="lucide-chevron-up size-4" aria-hidden="true" />
          </button>
          <button type="button" class="grid size-7 place-items-center rounded-full text-[#54656F] hover:bg-[#F0F2F5]" title="Next match" @click="showMatch(matchCursor + 1)">
            <span class="lucide-chevron-down size-4" aria-hidden="true" />
          </button>
        </div>

        <div
          v-if="presenceLabel"
          class="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs font-medium text-amber-900"
        >
          {{ presenceLabel }}
        </div>

        <div v-if="notesOpen" class="border-b border-outline-gray-2 bg-amber-50/70 px-4 py-3">
          <p class="text-xs text-ink-gray-6">Internal notes stay on this conversation. They are never sent on WhatsApp.</p>
          <ul v-if="notes.length" class="mt-2 max-h-36 space-y-2 overflow-y-auto">
            <li v-for="note in notes" :key="note.name" class="rounded-md bg-white px-3 py-2 text-xs">
              <div class="font-semibold text-ink-gray-8">{{ note.author || 'Agent' }}</div>
              <div class="mt-0.5 whitespace-pre-wrap text-ink-gray-7">{{ note.content }}</div>
            </li>
          </ul>
          <form class="mt-2 flex items-center gap-2" @submit.prevent="saveNote">
            <TextInput v-model="noteText" class="min-w-0 flex-1" placeholder="Add an internal note" />
            <Button type="submit" size="sm" variant="solid" label="Save" :loading="savingNote" :disabled="!noteText.trim()" />
          </form>
        </div>

        <!-- Message History Canvas -->
        <div ref="scroller" class="wa-chat-wallpaper min-h-0 min-w-0 flex-1 overflow-y-auto px-3 py-3 sm:px-6 md:px-10">
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
          <Button
            size="sm"
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E] shrink-0"
            label="Select Template to Send"
            icon-left="lucide-layout-template"
            @click="templateOpen = true"
          />
        </div>

        <!-- Message Composer Input -->
        <div
          v-if="current.profile.status !== 'Blocked'"
          class="shrink-0 border-t border-[#E9EDEF] bg-[#F0F2F5] px-2 py-2 sm:px-3"
        >
          <MessageInput
            v-bind="composer"
            :sender-name="current.profile.profile_name"
            placeholder="Type a message... (Shift+Enter for newline)"
            window-closed-label=""
            window-unopened-label=""
          >
            <template #leading-actions>
              <button
                type="button"
                class="grid size-10 place-items-center rounded-full text-[#54656F] hover:bg-black/5"
                title="Quick replies"
                @click="openQuickReplies"
              >
                <span class="lucide-zap size-5" aria-hidden="true" />
              </button>
              <button
                type="button"
                class="hidden size-10 place-items-center rounded-full text-[#54656F] hover:bg-black/5 sm:grid"
                title="Send template"
                @click="templateOpen = true"
              >
                <span class="lucide-layout-template size-5" aria-hidden="true" />
              </button>
              <button
                type="button"
                class="hidden size-10 place-items-center rounded-full text-[#54656F] hover:bg-black/5 sm:grid"
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
        class="inbox-rail inbox-rail-open relative hidden h-auto min-h-0 flex-col self-stretch border-l border-[#E9EDEF] bg-white md:flex"
      >
        <div class="flex h-14 shrink-0 items-center gap-2 border-b border-[#E9EDEF] px-2">
          <button
            type="button"
            class="grid size-8 shrink-0 place-items-center rounded-full text-[#54656F] hover:bg-[#F0F2F5]"
            title="Collapse contact info"
            aria-label="Collapse contact info"
            @click="contactOpen = false"
          >
            <span class="lucide-panel-right-close size-4" aria-hidden="true" />
          </button>
          <span class="truncate text-sm font-semibold text-[#111B21]">Contact info</span>
        </div>
        <ProfileDetails
          ref="desktopProfile"
          class="min-h-0 flex-1 overflow-y-auto"
          :thread="current"
          :assignment="currentAssignment"
          @assign="(user) => { assignUser = user; assignToUser(); }"
          @unassign="clearAssignment"
        />
      </aside>
    </section>

    <div v-if="details && current" class="fixed inset-0 z-50 md:hidden">
      <button type="button" class="absolute inset-0 bg-black/40" aria-label="Close contact info" @click="details = false" />
      <aside class="absolute inset-x-0 bottom-0 flex max-h-[min(70dvh,32rem)] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-xl">
        <div class="flex h-11 shrink-0 items-center justify-between border-b border-[#E9EDEF] px-3">
          <span class="text-sm font-semibold text-[#111B21]">Contact info</span>
          <button type="button" class="grid size-8 place-items-center rounded-full text-[#54656F] hover:bg-[#F0F2F5]" aria-label="Close" @click="details = false">
            <span class="lucide-x size-4" aria-hidden="true" />
          </button>
        </div>
        <ProfileDetails
          ref="drawerProfile"
          class="min-h-0 overflow-y-auto"
          :thread="current"
          :assignment="currentAssignment"
          @assign="(user) => { assignUser = user; assignToUser(); }"
          @unassign="clearAssignment"
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
          <div class="flex items-center gap-1 text-xs">
            <button
              type="button"
              class="rounded-lg px-2.5 py-1 font-medium"
              :class="templateTypeFilter === 'all' ? 'bg-[#075E54] text-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
              @click="templateTypeFilter = 'all'"
            >
              All
            </button>
            <button
              type="button"
              class="rounded-lg px-2.5 py-1 font-medium"
              :class="templateTypeFilter === 'Utility' ? 'bg-[#075E54] text-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
              @click="templateTypeFilter = 'Utility'"
            >
              Utility
            </button>
            <button
              type="button"
              class="rounded-lg px-2.5 py-1 font-medium"
              :class="templateTypeFilter === 'Marketing' ? 'bg-[#075E54] text-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
              @click="templateTypeFilter = 'Marketing'"
            >
              Marketing
            </button>
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
                  ? 'border-[#075E54] bg-teal-50/60 shadow-xs ring-1 ring-[#075E54]'
                  : 'border-outline-gray-2 hover:border-outline-gray-4 hover:bg-surface-gray-1'
              "
              @click="chooseTemplate(template)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-semibold text-ink-gray-9">
                  {{ template.template_label || template.name }}
                </span>
                <span
                  class="rounded-full px-2 py-0.5 text-[10px] font-medium"
                  :class="template.status === 'Approved' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'"
                >
                  {{ template.status }}
                </span>
              </div>
              <p class="mt-1 line-clamp-2 text-xs text-ink-gray-6">{{ template.message }}</p>
              <div class="mt-2 flex items-center gap-2 text-[10px] text-ink-gray-5">
                <span class="font-medium text-[#075E54]">{{ template.template_type }}</span>
                <span>·</span>
                <span>{{ template.language }}</span>
                <span v-if="template.buttons?.length">· {{ template.buttons.length }} buttons</span>
              </div>
            </button>
          </div>

          <!-- Live WhatsApp Bubble Preview -->
          <div class="flex min-h-0 flex-col overflow-y-auto rounded-xl border border-outline-gray-2 bg-[#efeae2]/40 p-4">
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
            Selected: <strong>{{ picked.template_label || picked.name }}</strong>
          </span>
          <span v-else />
          <div class="flex gap-2">
            <Button label="Cancel" @click="templateOpen = false" />
            <Button
              variant="solid"
              class="bg-[#075E54] text-white hover:bg-[#128C7E]"
              label="Send Template"
              icon-left="lucide-send"
              :disabled="!picked"
              :loading="desk.sending.value"
              @click="sendPicked"
            />
          </div>
        </div>
      </template>
    </Dialog>

    <!-- Quick Replies Modal Dialog -->
    <Dialog v-model="quickOpen" title="Insert Quick Reply">
      <div class="space-y-3">
        <TextInput
          v-model="quickQuery"
          placeholder="Filter quick replies…"
          class="w-full"
        />
        <div class="grid max-h-96 gap-2 overflow-y-auto">
          <button
            v-for="row in filteredQuickReplies"
            :key="row.name"
            type="button"
            class="rounded-xl border border-outline-gray-2 p-3 text-left transition-colors hover:border-[#128C7E] hover:bg-surface-gray-1"
            @click="insertQuickReply(row.name)"
          >
            <span class="block text-sm font-semibold text-ink-gray-9">{{ row.title }}</span>
            <span class="mt-1 block text-xs text-ink-gray-6 leading-relaxed">{{ row.body }}</span>
          </button>
          <p v-if="!filteredQuickReplies.length" class="py-6 text-center text-xs text-ink-gray-5">
            No active quick replies match your search.
          </p>
        </div>
      </div>
      <template #actions>
        <Button label="Close" @click="quickOpen = false" />
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
          <span class="lucide-loader-2 size-4 animate-spin text-[#075E54]" />
          <p class="mt-2">Loading catalog items…</p>
        </div>
        <div v-else-if="!filteredCatalogItems.length" class="py-8 text-center text-xs text-ink-gray-5">
          No catalog items found. Manage products under <strong>Integrations → Catalogs</strong>.
        </div>
        <div v-else class="grid max-h-96 gap-2.5 overflow-y-auto">
          <div
            v-for="item in filteredCatalogItems"
            :key="item.name"
            class="flex items-center justify-between gap-3 rounded-xl border border-outline-gray-2 p-3 hover:border-outline-gray-4 transition-colors bg-white"
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
              :loading="catalogSending && catalogSendingItem === item.name"
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
  </div>
</template>
