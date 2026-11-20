<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Badge, Button, Dialog, FormControl, Select, TextInput, toast } from 'frappe-ui'
import DeskTemplatePreview from '@/components/DeskTemplatePreview.vue'
import EmptyState from '@/components/EmptyState.vue'
import TemplateButtonFields from '@/components/templates/TemplateButtonFields.vue'
import { errorText, initials } from '@/utils/format'
import {
  deleteWhatsappTemplate,
  getWhatsappTemplate,
  listWhatsappLanguages,
  saveWhatsappTemplate,
  syncWhatsappTemplates,
} from '@/services/catalogApi'
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
const countAuthentication = computed(() => templates.value.filter((t) => t.template_type === 'Authentication').length)

const languageRows = ref<Array<{ value: string; label: string }>>([])
const languagesLoading = ref(false)

function defaultLanguageCode() {
  const rows = languageRows.value
  for (const code of ['en_US', 'en']) {
    if (rows.some((row) => row.value === code)) return code
  }
  return rows[0]?.value || ''
}

async function loadLanguages() {
  if (!live) {
    languageRows.value = []
    return
  }
  if (languagesLoading.value) return
  languagesLoading.value = true
  try {
    const rows = await listWhatsappLanguages()
    languageRows.value = Array.isArray(rows)
      ? rows.map((row) => ({
          value: row.value || row.language_code || '',
          label: row.label || row.language_name || row.value || row.language_code || '',
        })).filter((row) => row.value)
      : []
  } catch (caught) {
    languageRows.value = []
    toast.error(errorText(caught))
  } finally {
    languagesLoading.value = false
  }
}

onMounted(() => {
  void loadLanguages()
})

function applyKpiFilter(kind: 'Approved' | 'Pending' | 'Utility' | 'Marketing' | 'Authentication') {
  if (kind === 'Approved' || kind === 'Pending') {
    selectedStatus.value = kind
    selectedCategory.value = 'all'
    return
  }
  selectedCategory.value = kind
  selectedStatus.value = 'All'
}

const categoryOptions = computed(() => [
  { label: 'All Categories', value: 'all' },
  { label: `Utility (${countUtility.value})`, value: 'Utility' },
  { label: `Marketing (${countMarketing.value})`, value: 'Marketing' },
  { label: `Auth (${countAuthentication.value})`, value: 'Authentication' },
])

const templateTypeOptions = [
  { label: 'Marketing', value: 'Marketing' },
  { label: 'Utility', value: 'Utility' },
  { label: 'Authentication', value: 'Authentication' },
]

const headerTypeOptions = [
  { label: 'Text', value: 'Text' },
  { label: 'Image', value: 'Image' },
  { label: 'Document', value: 'Document' },
  { label: 'GIF', value: 'GIF' },
  { label: 'Video', value: 'Video' },
]

// Account options
const accountOptions = computed(() => {
  const accs = desk.inbox.value?.accounts || []
  return [
    { label: 'All Accounts', value: 'all' },
    ...accs.map((a) => ({ label: a.account_name || a.name, value: a.name })),
  ]
})

const editorAccountOptions = computed(() =>
  (desk.inbox.value?.accounts || []).map((a) => ({
    label: a.account_name || a.name,
    value: a.name,
  })),
)

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
const templateDeleteOpen = ref(false)
const templateSaving = ref(false)
const templateForm = ref({
  name: '',
  template_label: '',
  template_type: 'Marketing',
  message: '',
  footer: '',
  header_text: '',
  header_type: 'Text',
  language: 'en_US',
  whatsapp_account: '',
  status: '',
  whatsapp_template_id: '',
  buttons: [] as Array<{ button_type: string; button_text: string; url: string; phone_number: string }>,
})
const syncingTemplates = ref(false)
const buttonsReady = ref(true)

const languageOptions = computed(() => {
  const rows = [...languageRows.value]
  const current = templateForm.value.language
  if (current && !rows.some((row) => row.value === current)) {
    rows.unshift({ label: current, value: current })
  }
  return rows
})

const editorPreview = computed<Template>(() => ({
  name: templateForm.value.name || 'draft',
  template_label: templateForm.value.template_label || 'Untitled template',
  template_type: templateForm.value.template_type,
  language: templateForm.value.language || 'en_US',
  status: templateForm.value.status || (templateForm.value.whatsapp_template_id ? 'Pending' : 'Draft'),
  header_type: templateForm.value.header_type,
  header_text: templateForm.value.header_text,
  message: templateForm.value.message || 'Message body will appear here…',
  footer: templateForm.value.footer,
  whatsapp_account: templateForm.value.whatsapp_account,
  buttons: templateForm.value.buttons.filter((row) => row.button_text.trim()),
}))

const editorOnMeta = computed(() => Boolean(templateForm.value.whatsapp_template_id))
const editorPendingReview = computed(() => templateForm.value.status === 'Pending' && editorOnMeta.value)
const editorLocked = computed(() => editorPendingReview.value)

function blankButton() {
  return { button_type: 'Quick Reply', button_text: '', url: '', phone_number: '' }
}

function validateTemplateForm(forMeta: boolean): string | null {
  if (!templateForm.value.template_label.trim() || !templateForm.value.message.trim()) {
    return 'Label and message are required.'
  }
  if (!templateForm.value.whatsapp_account) {
    return 'Choose a WhatsApp account.'
  }
  const buttons = templateForm.value.buttons.filter((row) => row.button_text.trim())
  if (buttons.length > 3) {
    return 'Meta allows at most 3 buttons on a template.'
  }
  if (!forMeta) return null
  for (const button of buttons) {
    if (button.button_type === 'URL' && !button.url.trim()) {
      return `URL button “${button.button_text}” needs a link.`
    }
    if (button.button_type === 'Phone Number' && !button.phone_number.trim()) {
      return `Phone button “${button.button_text}” needs a number.`
    }
  }
  return null
}

async function openTemplateEditor(template?: Template) {
  if (live && !languageRows.value.length) await loadLanguages()
  const accounts = desk.inbox.value?.accounts || []
  templateForm.value = {
    name: template?.name && template.name !== 'new' ? template.name : '',
    template_label: template?.template_label || '',
    template_type: template?.template_type || 'Marketing',
    message: template?.message || '',
    footer: template?.footer || '',
    header_text: template?.header_text || '',
    header_type: template?.header_type || 'Text',
    language: template?.language || defaultLanguageCode(),
    whatsapp_account: template?.whatsapp_account || accounts[0]?.name || '',
    status: template?.status || '',
    whatsapp_template_id: '',
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
    templateForm.value.status = full.status || templateForm.value.status
    templateForm.value.whatsapp_template_id = full.whatsapp_template_id || ''
    templateForm.value.template_type = full.template_type || templateForm.value.template_type
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

async function persistTemplate(submitToMeta: boolean) {
  const issue = validateTemplateForm(submitToMeta)
  if (issue) {
    toast.error(issue)
    return
  }
  if (!live) {
    toast.success(submitToMeta ? 'Template submitted in the sample.' : 'Template saved in the sample.')
    templateEditorOpen.value = false
    return
  }
  if (submitToMeta && editorLocked.value) {
    toast.error('This template is pending Meta review. Wait for approval or rejection before resubmitting.')
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
      language: templateForm.value.language.trim() || 'en_US',
      footer: templateForm.value.footer.trim() || undefined,
      header_text: templateForm.value.header_text.trim() || undefined,
      header_type: templateForm.value.header_type,
      buttons: buttonsReady.value ? templateForm.value.buttons.filter((row) => row.button_text.trim()) : undefined,
      submit_to_meta: submitToMeta,
    })
    templateEditorOpen.value = false
    toast.success(
      submitToMeta
        ? editorOnMeta.value
          ? 'Template update sent to Meta.'
          : 'Template submitted to Meta for review.'
        : 'Template saved in Nudg (not submitted to Meta).',
    )
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
  if (selectedAccount.value === 'all') {
    toast.success('Syncing templates for every WhatsApp account you can manage…')
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
  templateSaving.value = true
  try {
    if (live) await deleteWhatsappTemplate(templateForm.value.name)
    if (selected.value === templateForm.value.name) selected.value = null
    templateDeleteOpen.value = false
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
        <button
          type="button"
          class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5 text-left transition-colors hover:border-[#128C7E]"
          @click="applyKpiFilter('Approved')"
        >
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Approved Templates</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-emerald-700">{{ countApproved }}</span>
            <span class="text-[11px] text-ink-gray-5">/ {{ countTotal }} total</span>
          </div>
        </button>

        <button
          type="button"
          class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5 text-left transition-colors hover:border-[#128C7E]"
          @click="applyKpiFilter('Pending')"
        >
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Pending Review</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-amber-700">{{ countPending }}</span>
            <span class="text-[11px] font-medium text-amber-600">with Meta</span>
          </div>
        </button>

        <button
          type="button"
          class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5 text-left transition-colors hover:border-[#128C7E]"
          @click="applyKpiFilter('Utility')"
        >
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Utility Alerts</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-[#075E54]">{{ countUtility }}</span>
            <span class="text-[11px] text-ink-gray-5">operational</span>
          </div>
        </button>

        <button
          type="button"
          class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5 text-left transition-colors hover:border-[#128C7E]"
          @click="applyKpiFilter('Marketing')"
        >
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Marketing Broadcasts</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-purple-700">{{ countMarketing }}</span>
            <span class="text-[11px] text-ink-gray-5">promotional</span>
          </div>
        </button>
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
          <Select
            class="w-40 text-xs"
            :model-value="selectedCategory"
            :options="categoryOptions"
            @update:model-value="(val) => (selectedCategory = (String(val || 'all') as typeof selectedCategory))"
          />

          <Select
            class="w-32 text-xs"
            :model-value="selectedStatus"
            :options="statuses"
            @update:model-value="(val) => (selectedStatus = String(val || 'All'))"
          />

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

        <!-- Recipient Search & Selector (custom list — no frappe-ui picker with avatar + phone rows) -->
        <div class="space-y-2">
          <TextInput
            v-model="recipientSearch"
            label="Select customer recipient"
            placeholder="Search customer by name or phone…"
            class="w-full"
            required
          />

          <div class="max-h-48 overflow-y-auto divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2 bg-white">
            <button
              v-for="r in filteredRecipients"
              :key="r.value"
              type="button"
              class="flex w-full items-center justify-between p-2.5 text-left transition-colors hover:bg-surface-gray-1"
              :class="recipient === r.value ? 'bg-teal-50/70 font-semibold text-[#075E54]' : 'text-ink-gray-8'"
              @click="recipient = r.value"
            >
              <div class="flex min-w-0 items-center gap-2">
                <span class="grid size-7 shrink-0 place-items-center rounded-full bg-teal-100 text-[10px] font-bold text-[#075E54]">
                  {{ initials(r.name) }}
                </span>
                <div class="min-w-0">
                  <p class="truncate text-xs">{{ r.name }}</p>
                  <p class="font-mono text-[11px] text-ink-gray-5">{{ r.phone }}</p>
                </div>
              </div>
              <span v-if="recipient === r.value" class="lucide-check size-4 shrink-0 text-[#075E54]" />
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

    <Dialog
      v-model="templateEditorOpen"
      :title="templateForm.name ? 'Edit template' : 'New template'"
      size="7xl"
    >
      <div class="grid max-h-[min(70vh,40rem)] min-h-0 grid-cols-1 gap-4 md:grid-cols-2">
        <div class="min-h-0 space-y-3 overflow-y-auto py-1 text-xs pr-1">
          <div
            v-if="editorPendingReview"
            class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900"
          >
            Pending Meta review. Local draft saves are allowed; submitting again is blocked until Meta responds.
          </div>
          <div
            v-else-if="editorOnMeta"
            class="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-900"
          >
            Linked to Meta template ID <span class="font-mono">{{ templateForm.whatsapp_template_id }}</span>.
            Save draft keeps Nudg only; Submit updates Meta.
          </div>
          <p v-else class="text-ink-gray-6">
            Save a local draft first, then submit to Meta when the content is ready for review.
          </p>

          <FormControl
            v-model="templateForm.template_label"
            type="text"
            label="Label"
            required
            :disabled="editorLocked"
          />
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormControl
              v-model="templateForm.template_type"
              type="select"
              label="Type"
              :options="templateTypeOptions"
              :disabled="editorLocked || editorOnMeta"
            />
            <FormControl
              v-model="templateForm.whatsapp_account"
              type="select"
              label="WhatsApp account"
              :options="editorAccountOptions"
              :disabled="editorLocked || editorOnMeta"
            />
          </div>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormControl
              v-model="templateForm.language"
              type="select"
              label="Language"
              :options="languageOptions"
              :disabled="editorLocked || editorOnMeta || languagesLoading"
              :description="languagesLoading ? 'Loading languages…' : languageOptions.length ? undefined : 'No WA Language records on this site'"
            />
            <FormControl
              v-model="templateForm.header_type"
              type="select"
              label="Header type"
              :options="headerTypeOptions"
              :disabled="editorLocked"
            />
          </div>
          <FormControl
            v-if="templateForm.header_type === 'Text'"
            v-model="templateForm.header_text"
            type="text"
            label="Header text"
            :disabled="editorLocked"
          />
          <p v-else class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-ink-gray-6">
            Header media upload for {{ templateForm.header_type }} samples is coming next. You can still draft body and buttons.
          </p>
          <FormControl
            v-model="templateForm.message"
            type="textarea"
            label="Message"
            required
            :rows="4"
            :disabled="editorLocked"
          />
          <FormControl
            v-model="templateForm.footer"
            type="text"
            label="Footer"
            :disabled="editorLocked"
          />
          <div class="space-y-2">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-semibold text-ink-gray-7">Buttons (max 3)</span>
              <Button
                size="sm"
                variant="subtle"
                label="Add button"
                :disabled="editorLocked || templateForm.buttons.length >= 3"
                @click="templateForm.buttons.push(blankButton())"
              />
            </div>
            <TemplateButtonFields
              v-for="(row, rowIndex) in templateForm.buttons"
              :key="rowIndex"
              v-model="templateForm.buttons[rowIndex]"
              :disabled="editorLocked"
              @remove="templateForm.buttons.splice(rowIndex, 1)"
            />
          </div>
        </div>

        <div class="min-h-0 overflow-y-auto rounded-xl border border-outline-gray-2 bg-[#efeae2]/40 p-4">
          <p class="mb-3 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-ink-gray-5">
            <span class="lucide-smartphone size-3.5 text-[#075E54]" />
            Live WhatsApp Preview
          </p>
          <DeskTemplatePreview :template="editorPreview" mode="preview" :editable="false" large />
        </div>
      </div>

      <template #actions>
        <div class="flex w-full flex-wrap items-center justify-between gap-2">
          <Button
            v-if="templateForm.name"
            variant="subtle"
            label="Delete"
            :loading="templateSaving"
            @click="templateDeleteOpen = true"
          />
          <span v-else />
          <div class="flex flex-wrap gap-2">
            <Button variant="subtle" label="Cancel" @click="templateEditorOpen = false" />
            <Button
              variant="subtle"
              label="Save draft"
              :loading="templateSaving || Boolean(templateForm.name && !buttonsReady)"
              :disabled="Boolean(templateForm.name && !buttonsReady)"
              @click="persistTemplate(false)"
            />
            <Button
              variant="solid"
              class="bg-[#075E54] text-white hover:bg-[#128C7E]"
              :label="editorOnMeta ? 'Update on Meta' : 'Submit to Meta'"
              :loading="templateSaving || Boolean(templateForm.name && !buttonsReady)"
              :disabled="Boolean(templateForm.name && !buttonsReady) || editorLocked"
              @click="persistTemplate(true)"
            />
          </div>
        </div>
      </template>
    </Dialog>

    <Dialog v-model="templateDeleteOpen" title="Delete template">
      <p class="text-sm text-ink-gray-7">
        Remove
        <strong>{{ templateForm.template_label || templateForm.name }}</strong>
        from Nudg? Meta is unchanged until the next sync.
      </p>
      <template #actions>
        <div class="flex w-full justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="templateDeleteOpen = false" />
          <Button variant="solid" theme="red" label="Delete" :loading="templateSaving" @click="removeTemplate" />
        </div>
      </template>
    </Dialog>
  </div>
</template>
