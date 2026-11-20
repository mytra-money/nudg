<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Badge, Button, Dialog, Select, TextInput, toast } from 'frappe-ui'
import DeskTemplatePreview from '@/components/DeskTemplatePreview.vue'
import EmptyState from '@/components/EmptyState.vue'
import { errorText, initials } from '@/utils/format'
import { deleteWhatsappTemplate, getWhatsappTemplate, saveWhatsappTemplate, syncWhatsappTemplates } from '@/services/catalogApi'
import { isManager, useDesk } from '@/stores/desk'
import type { Template } from '@/types'

const desk = useDesk()
const live = Boolean(window.csrf_token)

const narrow = useMediaQuery('(max-width: 767px)')
const showDetail = ref(false)
const query = ref('')
const selectedCategory = ref<'all' | 'Utility' | 'Marketing' | 'Authentication'>('all')
const selectedStatus = ref<string>('All')
const selectedAccount = ref<string>('all')

const selected = ref<string | null>(null)
const studioMode = ref<'preview' | 'raw'>('preview')

const sending = ref<Template | null>(null)
const recipient = ref('')
const recipientSearch = ref('')

const statuses = ['All', 'Approved', 'Pending', 'Rejected', 'Deleted']
const theme: Record<string, 'green' | 'amber' | 'red' | 'gray'> = {
  Approved: 'green',
  Pending: 'amber',
  Rejected: 'red',
  Deleted: 'gray',
}

const templates = computed(() => desk.inbox.value?.templates || [])

// KPI metrics
const countTotal = computed(() => templates.value.length)
const countApproved = computed(() => templates.value.filter((t) => t.status === 'Approved').length)
const countPending = computed(() => templates.value.filter((t) => t.status === 'Pending').length)
const countUtility = computed(() => templates.value.filter((t) => t.template_type === 'Utility').length)
const countMarketing = computed(() => templates.value.filter((t) => t.template_type === 'Marketing').length)

// Account options
const accountOptions = computed(() => {
  const accs = desk.inbox.value?.accounts || []
  return [
    { label: 'All Accounts', value: 'all' },
    ...accs.map((a) => ({ label: a.account_name || a.name, value: a.name })),
  ]
})

// Filtered templates list
const visible = computed(() =>
  templates.value.filter((template) => {
    // Search
    if (query.value.trim()) {
      const q = query.value.toLowerCase()
      const haystack = `${template.template_label} ${template.template_name || ''} ${template.message} ${template.reference_doctype || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }

    // Category
    if (selectedCategory.value !== 'all' && template.template_type !== selectedCategory.value) {
      return false
    }

    // Status
    if (selectedStatus.value !== 'All' && template.status !== selectedStatus.value) {
      return false
    }

    // Account
    if (selectedAccount.value !== 'all' && template.whatsapp_account && template.whatsapp_account !== selectedAccount.value) {
      return false
    }

    return true
  }),
)

const current = computed(
  () => visible.value.find((template) => template.name === selected.value) || visible.value[0] || null,
)

const recipients = computed(() =>
  (desk.inbox.value?.conversations || [])
    .filter((row) => desk.account.value === 'all' || row.profile.whatsapp_account === desk.account.value)
    .map((row) => ({
      label: `${row.profile.profile_name} · ${row.profile.phone_number}`,
      value: row.profile.name,
      phone: row.profile.phone_number,
      name: row.profile.profile_name,
    })),
)

const filteredRecipients = computed(() => {
  if (!recipientSearch.value.trim()) return recipients.value
  const q = recipientSearch.value.toLowerCase()
  return recipients.value.filter(
    (r) => r.label.toLowerCase().includes(q) || r.phone.toLowerCase().includes(q),
  )
})

function startSending(template: Template) {
  sending.value = template
  recipient.value = recipients.value[0]?.value || ''
  recipientSearch.value = ''
}

async function send() {
  if (!sending.value || !recipient.value) return
  await desk.openProfile(recipient.value)
  await desk.sendTemplate(sending.value)
  sending.value = null
  toast.success('Template sent to conversation!')
}

function selectTemplate(t: Template) {
  selected.value = t.name
  showDetail.value = true
}

const templateEditorOpen = ref(false)
const templateSaving = ref(false)
const templateForm = ref({
  name: '',
  template_label: '',
  template_type: 'Marketing',
  message: '',
  footer: '',
  header_text: '',
  header_type: 'Text',
  language: 'en',
  whatsapp_account: '',
  buttons: [] as Array<{ button_type: string; button_text: string; url: string; phone_number: string }>,
})
const syncingTemplates = ref(false)
const buttonsReady = ref(true)

function blankButton() {
  return { button_type: 'Quick Reply', button_text: '', url: '', phone_number: '' }
}

async function openTemplateEditor(template?: Template) {
  const accounts = desk.inbox.value?.accounts || []
  templateForm.value = {
    name: template?.name && template.name !== 'new' ? template.name : '',
    template_label: template?.template_label || '',
    template_type: template?.template_type || 'Marketing',
    message: template?.message || '',
    footer: template?.footer || '',
    header_text: template?.header_text || '',
    header_type: template?.header_type || 'Text',
    language: template?.language || 'en',
    whatsapp_account: template?.whatsapp_account || accounts[0]?.name || '',
    buttons: (template?.buttons || []).map((row) => ({
      button_type: row.button_type || 'Quick Reply',
      button_text: row.button_text || '',
      url: row.url || '',
      phone_number: row.phone_number || '',
    })),
  }
  buttonsReady.value = !live || !templateForm.value.name
  templateEditorOpen.value = true
  if (!live || !templateForm.value.name) return
  try {
    const full = await getWhatsappTemplate(templateForm.value.name)
    if (!templateEditorOpen.value || templateForm.value.name !== full.name) return
    templateForm.value.header_type = full.header_type || templateForm.value.header_type
    templateForm.value.language = full.language || templateForm.value.language
    templateForm.value.header_text = full.header_text || ''
    templateForm.value.message = full.message || templateForm.value.message
    templateForm.value.footer = full.footer || ''
    templateForm.value.buttons = (full.buttons || []).map((row: any) => ({
      button_type: row.button_type || 'Quick Reply',
      button_text: row.button_text || '',
      url: row.url || '',
      phone_number: row.phone_number || '',
    }))
    buttonsReady.value = true
  } catch {
    buttonsReady.value = false
  }
}

async function saveTemplate() {
  if (!templateForm.value.template_label.trim() || !templateForm.value.message.trim()) {
    toast.error('Label and message are required.')
    return
  }
  if (!templateForm.value.whatsapp_account) {
    toast.error('Choose a WhatsApp account.')
    return
  }
  if (!live) {
    toast.success('Template saved in the sample.')
    templateEditorOpen.value = false
    return
  }
  templateSaving.value = true
  try {
    const saved = await saveWhatsappTemplate({
      name: templateForm.value.name || undefined,
      template_label: templateForm.value.template_label.trim(),
      message: templateForm.value.message.trim(),
      whatsapp_account: templateForm.value.whatsapp_account,
      template_type: templateForm.value.template_type,
      language: templateForm.value.language.trim() || 'en',
      footer: templateForm.value.footer.trim() || undefined,
      header_text: templateForm.value.header_text.trim() || undefined,
      header_type: templateForm.value.header_type,
      buttons: buttonsReady.value ? templateForm.value.buttons.filter((row) => row.button_text.trim()) : undefined,
    })
    templateEditorOpen.value = false
    toast.success('Template saved and sent to Meta.')
    if (saved?.name) selected.value = saved.name
    await desk.refresh()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    templateSaving.value = false
  }
}

async function syncTemplates() {
  if (!live) {
    toast.success('Sample templates are already loaded.')
    return
  }
  syncingTemplates.value = true
  try {
    const account = selectedAccount.value !== 'all' ? selectedAccount.value : undefined
    const result = await syncWhatsappTemplates(account)
    const created = result?.total_synced ?? result?.accounts?.reduce((sum: number, row: any) => sum + (row.total_synced || 0), 0) ?? 0
    toast.success(created ? `Synced ${created} new template${created === 1 ? '' : 's'} from Meta.` : 'Templates are up to date with Meta.')
    await desk.refresh()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    syncingTemplates.value = false
  }
}

async function removeTemplate() {
  if (!templateForm.value.name) return
  if (!window.confirm(`Delete template “${templateForm.value.template_label || templateForm.value.name}” from Nudg?`)) return
  templateSaving.value = true
  try {
    if (live) await deleteWhatsappTemplate(templateForm.value.name)
    if (selected.value === templateForm.value.name) selected.value = null
    templateEditorOpen.value = false
    toast.success('Template removed from Nudg.')
    if (live) await desk.refresh()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    templateSaving.value = false
  }
}

function clearFilters() {
  query.value = ''
  selectedCategory.value = 'all'
  selectedStatus.value = 'All'
  selectedAccount.value = 'all'
}
</script>

<template>
  <div class="flex h-full min-w-0 flex-col overflow-hidden bg-surface-gray-1">
    <!-- Top Action Header -->
    <header class="flex flex-col gap-3 border-b border-outline-gray-2 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between shrink-0">
      <div>
        <div class="flex items-center gap-2">
          <span class="rounded bg-[#075E54]/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-[#075E54]">
            Meta Cloud API
          </span>
          <span class="text-xs text-ink-gray-5">·</span>
          <span class="text-xs font-medium text-ink-gray-6">Template Studio & Library</span>
        </div>
        <h1 class="mt-1 text-xl font-bold tracking-tight text-ink-gray-9">
          WhatsApp Message Templates
        </h1>
      </div>
      <div v-if="isManager" class="flex flex-wrap gap-2">
        <Button
          variant="subtle"
          size="sm"
          label="Sync from Meta"
          :loading="syncingTemplates"
          @click="syncTemplates"
        />
        <Button
          variant="solid"
          size="sm"
          class="bg-[#075E54] text-white hover:bg-[#128C7E]"
          icon-left="lucide-plus"
          label="New Template"
          @click="openTemplateEditor()"
        />
      </div>
    </header>

    <!-- Top KPI Performance Bar -->
    <section class="border-b border-outline-gray-2 bg-white px-4 py-3 shrink-0">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <!-- Approved -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Approved Templates</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-emerald-700">{{ countApproved }}</span>
            <span class="text-[11px] text-ink-gray-5">/ {{ countTotal }} total</span>
          </div>
        </div>

        <!-- Pending Meta Review -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Pending Review</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-amber-700">{{ countPending }}</span>
            <span class="text-[11px] text-amber-600 font-medium">with Meta</span>
          </div>
        </div>

        <!-- Utility -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Utility Alerts</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-[#075E54]">{{ countUtility }}</span>
            <span class="text-[11px] text-ink-gray-5">operational</span>
          </div>
        </div>

        <!-- Marketing -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Marketing Broadcasts</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-purple-700">{{ countMarketing }}</span>
            <span class="text-[11px] text-ink-gray-5">promotional</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Filters & Search Toolbar -->
    <section class="border-b border-outline-gray-2 bg-white px-4 py-2.5 space-y-2 shrink-0">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
        <!-- Search Input -->
        <div class="relative flex-1 max-w-sm">
          <TextInput
            v-model="query"
            placeholder="Search templates by label, body, or doctype…"
            class="w-full text-xs"
          />
          <button
            v-if="query"
            type="button"
            class="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-gray-4 hover:text-ink-gray-7"
            @click="query = ''"
          >
            <span class="lucide-x size-3" />
          </button>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <!-- Category Tabs -->
          <div class="flex flex-wrap items-center gap-1 rounded-lg bg-surface-gray-2 p-0.5 text-xs">
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedCategory === 'all' ? 'bg-white text-ink-gray-9 shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedCategory = 'all'"
            >
              All Categories
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedCategory === 'Utility' ? 'bg-white text-[#075E54] shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedCategory = 'Utility'"
            >
              Utility ({{ countUtility }})
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedCategory === 'Marketing' ? 'bg-white text-purple-700 shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedCategory = 'Marketing'"
            >
              Marketing ({{ countMarketing }})
            </button>
          </div>

          <!-- Status Select -->
          <Select
            class="w-32 text-xs"
            :model-value="selectedStatus"
            :options="statuses"
            @update:model-value="(val) => (selectedStatus = String(val || 'All'))"
          />

          <!-- Account Select -->
          <Select
            class="w-36 text-xs"
            :model-value="selectedAccount"
            :options="accountOptions"
            @update:model-value="(val) => (selectedAccount = String(val || 'all'))"
          />
        </div>
      </div>
    </section>

    <!-- Master-Detail Studio Grid -->
    <div class="nudg-split nudg-master grid min-h-0 flex-1 grid-cols-1 overflow-hidden md:grid-cols-[minmax(0,1fr)_minmax(0,480px)]">
      <!-- Left Column: Template Library List -->
      <aside
        class="min-h-0 flex-col divide-y divide-outline-gray-1 overflow-y-auto border-r border-outline-gray-2 bg-white"
        :class="narrow && showDetail ? 'hidden' : 'flex'"
      >
        <EmptyState
          v-if="templates.length === 0"
          title="No templates yet"
          description="Sync from Meta or create a template. Approved templates can be sent from the inbox."
        />
        <div v-else-if="visible.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
          <div class="mx-auto grid size-10 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-4">
            <span class="lucide-layout-template size-5" />
          </div>
          <p class="mt-2 text-sm font-semibold text-ink-gray-8">No templates found</p>
          <p class="mt-1 text-ink-gray-5">No templates match your search query or selected filters.</p>
          <button
            type="button"
            class="mt-3 text-xs font-semibold text-[#075E54] hover:underline"
            @click="clearFilters"
          >
            Clear all filters
          </button>
        </div>

        <button
          v-for="template in visible"
          :key="template.name"
          type="button"
          class="flex w-full flex-col gap-2 p-4 text-left transition-all hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#128C7E]"
          :class="
            current?.name === template.name
              ? 'border-l-4 border-l-[#075E54] bg-teal-50/70 shadow-2xs'
              : 'border-l-4 border-l-transparent'
          "
          @click="selectTemplate(template)"
        >
          <div class="flex items-start justify-between gap-2">
            <div>
              <span class="font-bold text-sm text-ink-gray-9 leading-tight">
                {{ template.template_label || template.name }}
              </span>
              <p class="font-mono text-xs text-ink-gray-5 mt-0.5">
                {{ template.template_name || template.name }}
              </p>
            </div>
            <Badge
              :label="template.status"
              :theme="theme[template.status] || 'gray'"
              size="sm"
            />
          </div>

          <!-- Body preview with styled variable chips -->
          <p class="line-clamp-2 text-xs text-ink-gray-7 leading-relaxed">
            {{ template.message }}
          </p>

          <div class="flex flex-wrap items-center gap-1.5 text-[11px] pt-1">
            <span
              class="rounded px-1.5 py-0.2 font-medium"
              :class="template.template_type === 'Utility' ? 'bg-teal-50 text-[#075E54]' : 'bg-purple-50 text-purple-700'"
            >
              {{ template.template_type }}
            </span>
            <span class="rounded bg-surface-gray-2 px-1.5 py-0.2 font-mono text-ink-gray-6">
              {{ template.language }}
            </span>
            <span v-if="template.header_type" class="rounded bg-surface-gray-2 px-1.5 py-0.2 text-ink-gray-6">
              Header: {{ template.header_type }}
            </span>
            <span v-if="template.buttons?.length" class="rounded bg-blue-50 text-blue-700 px-1.5 py-0.2 font-medium">
              {{ template.buttons.length }} CTA buttons
            </span>
            <span v-if="template.reference_doctype" class="text-ink-gray-4 text-[10px] ml-auto">
              DocType: {{ template.reference_doctype }}
            </span>
          </div>
        </button>
      </aside>

      <!-- Right Column: Interactive Studio Inspector Canvas -->
      <main
        class="min-h-0 flex-col space-y-5 overflow-y-auto bg-white p-5 sm:p-6"
        :class="narrow && !showDetail ? 'hidden' : 'flex'"
      >
        <button
          v-if="narrow"
          type="button"
          class="inline-flex items-center gap-1 text-sm font-medium text-[#075E54]"
          @click="showDetail = false"
        >
          <span class="lucide-arrow-left size-4" aria-hidden="true" />
          All templates
        </button>
        <div v-if="current" class="space-y-5">
          <!-- Template Header & Metadata -->
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-outline-gray-2 pb-4">
            <div>
              <div class="flex items-center gap-2">
                <Badge
                  :label="current.status"
                  :theme="theme[current.status] || 'gray'"
                />
                <span class="rounded bg-surface-gray-2 px-2 py-0.5 text-xs font-medium text-ink-gray-7">
                  {{ current.template_type }}
                </span>
                <span class="rounded bg-surface-gray-2 px-2 py-0.5 text-xs font-mono text-ink-gray-6">
                  {{ current.language }}
                </span>
              </div>
              <h2 class="mt-2 text-xl font-bold text-ink-gray-9 leading-tight">
                {{ current.template_label || current.name }}
              </h2>
              <p class="font-mono text-xs text-ink-gray-5 mt-0.5">
                {{ current.template_name || current.name }}
                <span v-if="current.whatsapp_account"> · Channel: {{ current.whatsapp_account }}</span>
              </p>
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <Button
                v-if="isManager"
                variant="subtle"
                label="Edit"
                icon-left="lucide-pencil"
                @click="openTemplateEditor(current)"
              />
              <Button
                variant="solid"
                class="bg-[#075E54] text-white hover:bg-[#128C7E]"
                label="Send to Customer"
                icon-left="lucide-send"
                :disabled="current.status !== 'Approved'"
                @click="startSending(current)"
              />
            </div>
          </div>

          <!-- Mode Toggle (Preview vs Technical Raw Payload) -->
          <div class="flex flex-col gap-2 border-b border-outline-gray-2 pb-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex flex-wrap items-center gap-1 text-xs">
              <button
                type="button"
                class="rounded-lg px-3 py-1 font-semibold transition-colors"
                :class="studioMode === 'preview' ? 'bg-[#075E54] text-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
                @click="studioMode = 'preview'"
              >
                Interactive Preview
              </button>
              <button
                type="button"
                class="rounded-lg px-3 py-1 font-semibold transition-colors"
                :class="studioMode === 'raw' ? 'bg-[#075E54] text-white' : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
                @click="studioMode = 'raw'"
              >
                Raw Meta Specification
              </button>
            </div>

            <span class="text-[11px] leading-relaxed text-ink-gray-5">
              {{ current.status === 'Approved' ? 'Ready for chats and broadcasts' : 'Needs Meta approval before sending' }}
            </span>
          </div>

          <!-- Interactive WhatsApp Canvas Bubble -->
          <div class="rounded-xl border border-outline-gray-2 bg-[#efeae2]/40 p-4 shadow-inner">
            <p class="text-[11px] font-bold uppercase tracking-wider text-ink-gray-5 mb-3 flex items-center gap-1.5">
              <span class="lucide-smartphone size-3.5 text-[#075E54]" />
              WhatsApp Message Preview
            </p>
            <DeskTemplatePreview :template="current" :mode="studioMode" :editable="true" />
          </div>

          <!-- Variable Inspector (if parameters exist) -->
          <div v-if="current.template_variables?.length" class="rounded-xl border border-outline-gray-2 p-4 bg-white space-y-2.5">
            <h3 class="text-xs font-bold uppercase tracking-wider text-ink-gray-6 flex items-center gap-1.5">
              <span class="lucide-variable size-3.5 text-[#075E54]" />
              Dynamic Parameters & Sample Values
            </h3>
            <p class="text-xs text-ink-gray-5">
              These placeholders are dynamically replaced by Frappe DocType fields or API arguments:
            </p>
            <div class="divide-y divide-outline-gray-1 border rounded-lg border-outline-gray-2 overflow-hidden text-xs">
              <div
                v-for="v in current.template_variables"
                :key="v.variable_name"
                class="flex flex-wrap items-center gap-2 bg-white p-2.5"
              >
                <span class="font-mono font-bold text-[#075E54]">&#123;&#123;{{ v.variable_name }}&#125;&#125;</span>
                <span class="text-ink-gray-7">
                  Example: <strong>{{ v.variable_example || 'Sample Value' }}</strong>
                </span>
                <span v-if="v.variable_field" class="rounded bg-surface-gray-2 px-1.5 py-0.5 font-mono text-[11px] text-ink-gray-6">
                  {{ v.variable_field }}
                </span>
              </div>
            </div>
          </div>

          <!-- Interactive Action Buttons Specification -->
          <div v-if="current.buttons?.length" class="rounded-xl border border-outline-gray-2 p-4 bg-white space-y-2">
            <h3 class="text-xs font-bold uppercase tracking-wider text-ink-gray-6 flex items-center gap-1.5">
              <span class="lucide-mouse-pointer-click size-3.5 text-blue-600" />
              Quick Action Buttons ({{ current.buttons.length }})
            </h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div
                v-for="btn in current.buttons"
                :key="btn.button_text"
                class="rounded-lg border border-outline-gray-2 p-2.5 bg-surface-gray-1/40"
              >
                <div class="flex items-center justify-between">
                  <span class="font-semibold text-ink-gray-9">{{ btn.button_text }}</span>
                  <span class="rounded bg-blue-50 text-blue-700 px-1.5 py-0.2 text-[10px] font-medium">
                    {{ btn.button_type }}
                  </span>
                </div>
                <p v-if="btn.url" class="mt-1 font-mono text-[11px] text-ink-gray-5 truncate">
                  {{ btn.url }}
                </p>
                <p v-if="btn.phone_number" class="mt-1 font-mono text-[11px] text-ink-gray-5">
                  {{ btn.phone_number }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="grid flex-1 place-items-center p-8 text-center text-xs text-ink-gray-5">
          Select a template from the library on the left.
        </div>
      </main>
    </div>

    <!-- Send Template Modal Dialog -->
    <Dialog
      :open="Boolean(sending)"
      title="Send WhatsApp Template"
      size="lg"
      @update:open="(open) => !open && (sending = null)"
    >
      <div v-if="sending" class="space-y-4 py-2 text-xs">
        <div class="rounded-xl border border-teal-200 bg-teal-50 p-3.5 text-[#075E54] leading-relaxed">
          <p class="font-bold flex items-center gap-1.5">
            <span class="lucide-send size-4" /> Initiating Template Message
          </p>
          <p class="mt-1 text-ink-gray-7">
            Sending template <strong>{{ sending.template_label || sending.name }}</strong> ({{ sending.template_type }}). Templates can be delivered even when the customer's 24-hour service window is closed.
          </p>
        </div>

        <!-- Recipient Search & Selector -->
        <div>
          <label class="block text-xs font-semibold text-ink-gray-7 mb-1">Select Customer Recipient *</label>
          <TextInput
            v-model="recipientSearch"
            placeholder="Search customer by name or phone…"
            class="w-full mb-2"
          />

          <div class="max-h-48 overflow-y-auto divide-y divide-outline-gray-1 border border-outline-gray-2 rounded-lg bg-white">
            <button
              v-for="r in filteredRecipients"
              :key="r.value"
              type="button"
              class="flex items-center justify-between w-full p-2.5 text-left transition-colors hover:bg-surface-gray-1"
              :class="recipient === r.value ? 'bg-teal-50/70 text-[#075E54] font-semibold' : 'text-ink-gray-8'"
              @click="recipient = r.value"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span class="grid size-7 shrink-0 place-items-center rounded-full bg-teal-100 text-[10px] font-bold text-[#075E54]">
                  {{ initials(r.name) }}
                </span>
                <div class="min-w-0">
                  <p class="truncate text-xs">{{ r.name }}</p>
                  <p class="text-[11px] font-mono text-ink-gray-5">{{ r.phone }}</p>
                </div>
              </div>
              <span v-if="recipient === r.value" class="lucide-check size-4 text-[#075E54] shrink-0" />
            </button>
          </div>
        </div>

        <!-- Message Preview Bubble in Modal -->
        <div class="rounded-lg border border-outline-gray-2 bg-[#efeae2]/40 p-3">
          <p class="text-[10px] font-bold uppercase tracking-wider text-ink-gray-5 mb-2">Message Content</p>
          <DeskTemplatePreview :template="sending" mode="preview" :editable="false" />
        </div>
      </div>

      <template #actions>
        <div class="flex justify-between w-full">
          <Button label="Cancel" @click="sending = null" />
          <Button
            v-if="sending?.status === 'Approved'"
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Confirm & Send Template"
            icon-left="lucide-send"
            :disabled="!recipient"
            :loading="desk.sending.value"
            @click="send"
          />
        </div>
      </template>
    </Dialog>

    <Dialog v-model="templateEditorOpen" :title="templateForm.name ? 'Edit template' : 'New template'">
      <div class="space-y-3 py-1 text-xs">
        <p class="text-ink-gray-6">Saving sends this template to Meta for review. Approved templates can be used in campaigns and chats.</p>
        <label class="block">
          <span class="font-semibold text-ink-gray-7">Label</span>
          <input v-model="templateForm.template_label" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" />
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="font-semibold text-ink-gray-7">Type</span>
            <select v-model="templateForm.template_type" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2">
              <option>Marketing</option>
              <option>Utility</option>
              <option>Authentication</option>
            </select>
          </label>
          <label class="block">
            <span class="font-semibold text-ink-gray-7">WhatsApp account</span>
            <select v-model="templateForm.whatsapp_account" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2">
              <option v-for="account in desk.inbox.value?.accounts || []" :key="account.name" :value="account.name">
                {{ account.account_name || account.name }}
              </option>
            </select>
          </label>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="font-semibold text-ink-gray-7">Language</span>
            <input v-model="templateForm.language" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" placeholder="en" />
          </label>
          <label class="block">
            <span class="font-semibold text-ink-gray-7">Header type</span>
            <select v-model="templateForm.header_type" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2">
              <option>Text</option>
              <option>Image</option>
              <option>Document</option>
              <option>GIF</option>
              <option>Video</option>
            </select>
          </label>
        </div>
        <label class="block">
          <span class="font-semibold text-ink-gray-7">Header</span>
          <input v-model="templateForm.header_text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" />
        </label>
        <label class="block">
          <span class="font-semibold text-ink-gray-7">Message</span>
          <textarea v-model="templateForm.message" rows="4" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" />
        </label>
        <label class="block">
          <span class="font-semibold text-ink-gray-7">Footer</span>
          <input v-model="templateForm.footer" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" />
        </label>
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-semibold text-ink-gray-7">Buttons</span>
            <button type="button" class="text-[#075E54]" @click="templateForm.buttons.push(blankButton())">Add button</button>
          </div>
          <div v-for="(button, index) in templateForm.buttons" :key="index" class="grid grid-cols-2 gap-2 rounded-lg border border-outline-gray-2 p-2">
            <select v-model="button.button_type" class="rounded-lg border border-outline-gray-2 px-2 py-1.5">
              <option>Quick Reply</option>
              <option>URL</option>
              <option>Phone Number</option>
              <option>Copy Code</option>
              <option>Voice Call</option>
            </select>
            <input v-model="button.button_text" class="rounded-lg border border-outline-gray-2 px-2 py-1.5" placeholder="Button label" />
            <input v-if="button.button_type === 'URL'" v-model="button.url" class="col-span-2 rounded-lg border border-outline-gray-2 px-2 py-1.5" placeholder="https://" />
            <input v-if="button.button_type === 'Phone Number'" v-model="button.phone_number" class="col-span-2 rounded-lg border border-outline-gray-2 px-2 py-1.5" placeholder="Phone number" />
            <button type="button" class="col-span-2 text-left text-ink-gray-5" @click="templateForm.buttons.splice(index, 1)">Remove</button>
          </div>
        </div>
      </div>
      <template #actions>
        <div class="flex w-full items-center justify-between gap-2">
          <Button v-if="templateForm.name" variant="subtle" label="Delete" :loading="templateSaving" @click="removeTemplate" />
          <span v-else />
          <div class="flex gap-2">
            <Button variant="subtle" label="Cancel" @click="templateEditorOpen = false" />
            <Button
              variant="solid"
              class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Save"
            :loading="templateSaving || Boolean(templateForm.name && !buttonsReady)"
            :disabled="Boolean(templateForm.name && !buttonsReady)"
            @click="saveTemplate"
            />
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>
