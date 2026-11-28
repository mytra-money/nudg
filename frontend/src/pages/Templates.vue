<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Alert, Badge, Button, Dialog, FileUploader, FormControl, Select, TextInput, toast } from 'frappe-ui'
import DeskTemplatePreview from '@/components/DeskTemplatePreview.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import DeskSplit from '@/components/desk/DeskSplit.vue'
import TemplateButtonFields from '@/components/templates/TemplateButtonFields.vue'
import { errorText, initials } from '@/utils/format'
import { displayTitle } from '@/utils/titles'
import { fillVariables, mediaFileName, resolveSampleValues, variableNames } from '@/utils/templatePreview'
import {
  deleteWhatsappTemplate,
  getWhatsappTemplate,
  listWhatsappLanguages,
  saveWhatsappTemplate,
  syncWhatsappTemplates,
} from '@/services/catalogApi'
import { useAccountGate } from '@/composables/useAccountGate'
import { isManager, useDesk } from '@/stores/desk'
import type { Template } from '@/types'

const desk = useDesk()
const live = Boolean(window.csrf_token)

const narrow = useMediaQuery('(max-width: 767px)')
const showDetail = ref(false)
const query = ref('')
const selectedCategory = ref<'all' | 'Utility' | 'Marketing' | 'Authentication'>('all')
const selectedStatus = ref<string>('All')
const selected = ref<string | null>(null)

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

const { selectedAccount: currentAccount, selectedAccountLabel } = useAccountGate()

// Templates for the navbar number only (templates without an account are shared).
const templates = computed(() =>
  (desk.inbox.value?.templates || []).filter(
    (template) => !currentAccount.value || !template.whatsapp_account || template.whatsapp_account === currentAccount.value,
  ),
)

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
    selectedStatus.value = selectedStatus.value === kind ? 'All' : kind
    return
  }
  selectedCategory.value = selectedCategory.value === kind ? 'all' : kind
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
    return true
  }),
)

const current = computed(
  () => visible.value.find((template) => template.name === selected.value) || visible.value[0] || null,
)

const recipients = computed(() =>
  (desk.inbox.value?.conversations || [])
    .filter((row) => Boolean(currentAccount.value) && row.profile.whatsapp_account === currentAccount.value)
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
const templateAction = ref<'draft' | 'submit' | 'delete' | null>(null)
const templateForm = ref({
  name: '',
  template_label: '',
  template_type: 'Marketing',
  message: '',
  footer: '',
  header_text: '',
  header_type: 'Text',
  header_media: '',
  language: 'en_US',
  whatsapp_account: '',
  status: '',
  whatsapp_template_id: '',
  buttons: [] as Array<{ button_type: string; button_text: string; url: string; phone_number: string }>,
})
const variableExamples = ref<Record<string, string>>({})
const variableFields = ref<Record<string, string>>({})
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

const detectedVariableNames = computed(() =>
  variableNames(
    templateForm.value.header_type === 'Text' ? templateForm.value.header_text : '',
    templateForm.value.message,
  ),
)

const editorVariableRows = computed(() =>
  detectedVariableNames.value.map((name) => ({
    variable_name: name,
    variable_example: variableExamples.value[name] || '',
    variable_field: variableFields.value[name] || '',
  })),
)

const editorPreview = computed<Template>(() => ({
  name: templateForm.value.name || 'draft',
  template_label: templateForm.value.template_label || 'Untitled template',
  template_type: templateForm.value.template_type,
  language: templateForm.value.language || 'en_US',
  status: templateForm.value.status || (templateForm.value.whatsapp_template_id ? 'Pending' : 'Draft'),
  header_type: templateForm.value.header_type,
  header_text: templateForm.value.header_text,
  header_media: templateForm.value.header_media,
  message: templateForm.value.message || 'Message body will appear here…',
  footer: templateForm.value.footer,
  whatsapp_account: templateForm.value.whatsapp_account,
  buttons: templateForm.value.buttons.filter((row) => row.button_text.trim()),
  template_variables: editorVariableRows.value,
}))

const editorOnMeta = computed(() => Boolean(templateForm.value.whatsapp_template_id))
const editorPendingReview = computed(() => templateForm.value.status === 'Pending' && editorOnMeta.value)
const editorLocked = computed(() => editorPendingReview.value)

function blankButton() {
  return { button_type: 'Quick Reply', button_text: '', url: '', phone_number: '' }
}

function resetVariableExamples(
  rows?: Array<{ variable_name?: string; variable_example?: string; variable_field?: string }>,
) {
  const examples: Record<string, string> = {}
  const fields: Record<string, string> = {}
  for (const row of rows || []) {
    const name = (row.variable_name || '').trim()
    if (!name) continue
    examples[name] = row.variable_example || ''
    if (row.variable_field) fields[name] = row.variable_field
  }
  variableExamples.value = examples
  variableFields.value = fields
}

function setVariableExample(name: string, value: unknown) {
  variableExamples.value = { ...variableExamples.value, [name]: String(value ?? '') }
}

function variableLabel(name: string) {
  return `{{${name}}}`
}

const headerFileTypes = computed(() => {
  switch (templateForm.value.header_type) {
    case 'Image':
      return 'image/jpeg,image/png'
    case 'GIF':
      return 'image/gif'
    case 'Video':
      return 'video/mp4'
    case 'Document':
      return 'application/pdf'
    default:
      return ''
  }
})

const headerFileLabel = computed(() => mediaFileName(templateForm.value.header_media))

function onHeaderUploaded(file: { file_url?: string }) {
  if (!file?.file_url) {
    toast.error('Upload finished without a file address.')
    return
  }
  templateForm.value.header_media = file.file_url
}

function validateTemplateForm(forMeta: boolean): string | null {
  if (!templateForm.value.template_label.trim() || !templateForm.value.message.trim()) {
    return 'Label and message are required.'
  }
  if (!templateForm.value.whatsapp_account) {
    return 'Select a WhatsApp number in the top bar first.'
  }
  const buttons = templateForm.value.buttons.filter((row) => row.button_text.trim())
  if (buttons.length > 3) {
    return 'Meta allows at most 3 buttons on a template.'
  }
  if (forMeta && templateForm.value.header_type !== 'Text' && !templateForm.value.header_media) {
    return `Upload a sample ${templateForm.value.header_type.toLowerCase()} before submitting to Meta.`
  }
  for (const name of detectedVariableNames.value) {
    if (!(variableExamples.value[name] || '').trim()) {
      return `Add an example for {{${name}}}. Meta needs it to review the template.`
    }
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
  templateForm.value = {
    name: template?.name && template.name !== 'new' ? template.name : '',
    template_label: template?.template_label || '',
    template_type: template?.template_type || 'Marketing',
    message: template?.message || '',
    footer: template?.footer || '',
    header_text: template?.header_text || '',
    header_type: template?.header_type || 'Text',
    header_media: template?.header_media || '',
    language: template?.language || defaultLanguageCode(),
    whatsapp_account: currentAccount.value || '',
    status: template?.status || '',
    whatsapp_template_id: '',
    buttons: (template?.buttons || []).map((row) => ({
      button_type: row.button_type || 'Quick Reply',
      button_text: row.button_text || '',
      url: row.url || '',
      phone_number: row.phone_number || '',
    })),
  }
  resetVariableExamples(template?.template_variables)
  buttonsReady.value = !live || !templateForm.value.name
  templateEditorOpen.value = true
  if (!live || !templateForm.value.name) return
  try {
    const full = await getWhatsappTemplate(templateForm.value.name)
    if (!templateEditorOpen.value || templateForm.value.name !== full.name) return
    templateForm.value.header_type = full.header_type || templateForm.value.header_type
    templateForm.value.language = full.language || templateForm.value.language
    templateForm.value.header_text = full.header_text || ''
    templateForm.value.header_media = full.header_media || ''
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
    if (Array.isArray(full.template_variables)) resetVariableExamples(full.template_variables)
    buttonsReady.value = true
  } catch {
    buttonsReady.value = false
  }
}

async function persistTemplate(submitToMeta: boolean) {
  templateForm.value.whatsapp_account = currentAccount.value
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
  templateAction.value = submitToMeta ? 'submit' : 'draft'
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
      header_media: templateForm.value.header_type === 'Text' ? undefined : templateForm.value.header_media || undefined,
      buttons: buttonsReady.value ? templateForm.value.buttons.filter((row) => row.button_text.trim()) : undefined,
      template_variables: editorVariableRows.value.map((row) => ({
        variable_name: row.variable_name,
        variable_example: row.variable_example.trim(),
        variable_field: row.variable_field,
      })),
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
    templateAction.value = null
  }
}

async function syncTemplates() {
  if (!live) {
    toast.success('Sample templates are already loaded.')
    return
  }
  syncingTemplates.value = true
  try {
    const account = currentAccount.value || undefined
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
  templateAction.value = 'delete'
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
    templateAction.value = null
  }
}

function clearFilters() {
  query.value = ''
  selectedCategory.value = 'all'
  selectedStatus.value = 'All'
}

const filtersActive = computed(
  () => Boolean(query.value.trim()) || selectedCategory.value !== 'all' || selectedStatus.value !== 'All',
)

function listLine(template: Template) {
  const filled = fillVariables(template.message, resolveSampleValues(template)).replace(/\s+/g, ' ').trim()
  return filled || 'No message text'
}

function languageLabel(code?: string) {
  if (!code) return ''
  try {
    const display = new Intl.DisplayNames(['en'], { type: 'language' }).of(code.replaceAll('_', '-'))
    if (display && display.toLowerCase() !== code.toLowerCase()) return display
  } catch {
    /* use the stored language name */
  }
  const known = languageRows.value.find((row) => row.value === code)
  return known?.label && known.label !== code ? known.label : code
}
</script>

<template>
  <DeskPage variant="studio">
    <template #toolbar>
      <div class="flex items-center gap-2 overflow-x-auto">
        <div class="template-search relative">
          <TextInput
            v-model="query"
            placeholder="Search templates…"
            class="w-full text-xs"
          />
          <button
            v-if="query"
            type="button"
            class="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-gray-4 hover:text-ink-gray-7"
            aria-label="Clear search"
            @click="query = ''"
          >
            <span class="lucide-x size-3" />
          </button>
        </div>
        <Select
          class="w-36 shrink-0 text-xs"
          :model-value="selectedCategory"
          :options="categoryOptions"
          @update:model-value="(val) => (selectedCategory = (String(val || 'all') as typeof selectedCategory))"
        />
        <Select
          class="w-28 shrink-0 text-xs"
          :model-value="selectedStatus"
          :options="statuses"
          @update:model-value="(val) => (selectedStatus = String(val || 'All'))"
        />
        <Button
          v-if="filtersActive"
          variant="ghost"
          theme="green"
          size="sm"
          label="Clear"
          @click="clearFilters"
        />

        <div v-if="isManager" class="ml-auto flex flex-wrap items-center justify-end gap-2">
          <Button
            variant="subtle"
            size="sm"
            label="Sync from Meta"
            loading-text="Syncing…"
            :loading="syncingTemplates"
            @click="syncTemplates"
          />
          <Button variant="solid" theme="green" size="sm" icon-left="lucide-plus" label="New Template" @click="openTemplateEditor()"/>
        </div>
      </div>
    </template>

    <!-- Master-Detail Studio Grid -->
    <DeskSplit
      :narrow="narrow"
      :show-detail="showDetail"
      columns="minmax(200px,260px) minmax(0,1fr)"
    >
      <!-- Left Column: Template Library List -->
      <template #master>
      <div class="flex min-h-0 flex-1 flex-col divide-y divide-outline-gray-1 overflow-y-auto">
        <DeskEmpty
          v-if="templates.length === 0"
          kind="empty"
          title="No templates yet"
          description="Sync from Meta or create a template. Approved templates can be sent from the inbox."
        />
        <div v-else-if="visible.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
          <div class="mx-auto grid size-10 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-4">
            <span class="lucide-layout-template size-5" />
          </div>
          <p class="mt-2 text-sm font-semibold text-ink-gray-8">No templates found</p>
          <p class="mt-1 text-ink-gray-5">No templates match your search query or selected filters.</p>
          <Button
            variant="ghost"
            theme="green"
            size="sm"
            label="Clear all filters"
            class="mt-3"
            @click="clearFilters"
          />
        </div>

        <button
          v-for="template in visible"
          :key="template.name"
          type="button"
          class="flex w-full flex-col gap-1 px-3 py-2.5 text-left transition-all hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-green-3"
          :class="
            current?.name === template.name
              ? 'border-l-4 border-l-green-700 bg-teal-50/70 shadow-2xs'
              : 'border-l-4 border-l-transparent'
          "
          @click="selectTemplate(template)"
        >
          <div class="flex items-start justify-between gap-2">
            <span class="font-bold text-sm text-ink-gray-9 leading-tight">
              {{ displayTitle(template.template_label, template.template_name) || 'Untitled template' }}
            </span>
            <Badge
              v-if="template.status && template.status !== 'Draft'"
              :label="template.status"
              :theme="theme[template.status] || 'gray'"
              size="sm"
            />
          </div>

          <p class="line-clamp-1 text-xs leading-relaxed text-ink-gray-6">
            {{ listLine(template) }}
          </p>
        </button>
      </div>
      </template>

      <!-- Right Column: Interactive Studio Inspector Canvas -->
      <template #detail>
      <div class="flex min-h-0 flex-1 flex-col overflow-hidden bg-surface-base">
        <div v-if="current" class="flex min-h-0 flex-1 flex-col">
          <header class="shrink-0 border-b border-outline-gray-2 bg-surface-base px-3 py-2">
            <Button
              v-if="narrow"
              variant="ghost"
              theme="green"
              size="sm"
              icon-left="lucide-arrow-left"
              label="All templates"
              class="mb-2"
              @click="showDetail = false"
            />
            <div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <h2 class="min-w-0 truncate text-base font-semibold leading-tight text-ink-gray-9">
                    {{ displayTitle(current.template_label, current.template_name) || 'Untitled template' }}
                  </h2>
                  <Badge
                    v-if="current.status && current.status !== 'Draft'"
                    :label="current.status"
                    :theme="theme[current.status] || 'gray'"
                    size="sm"
                  />
                </div>
                <p class="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-ink-gray-6">
                  <span>{{ current.template_type }}</span>
                  <span class="text-ink-gray-4" aria-hidden="true">·</span>
                  <span>{{ languageLabel(current.language) }}</span>
                  <template v-if="current.header_type">
                    <span class="text-ink-gray-4" aria-hidden="true">·</span>
                    <span>{{ current.header_type }} header</span>
                  </template>
                  <template v-if="current.buttons?.length">
                    <span class="text-ink-gray-4" aria-hidden="true">·</span>
                    <span>{{ current.buttons.length }} {{ current.buttons.length === 1 ? 'button' : 'buttons' }}</span>
                  </template>
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <span v-if="current.status !== 'Approved'" class="text-[11px] font-medium text-amber-800">Waiting on Meta.</span>
                <Button
                  v-if="isManager"
                  variant="subtle"
                  size="sm"
                  label="Edit"
                  icon-left="lucide-pencil"
                  @click="openTemplateEditor(current)"
                />
                <Button variant="solid" theme="green" size="sm" label="Send to Customer" icon-left="lucide-send" :disabled="current.status !== 'Approved'" :title="current.status === 'Approved' ? 'Send this template' : 'Available after Meta approves this template'" @click="startSending(current)"/>
              </div>
            </div>
          </header>
          <div class="flex min-h-0 flex-1 items-start justify-center overflow-y-auto bg-surface-gray-1 p-4 sm:p-6">
            <div class="w-full max-w-[340px]">
              <DeskTemplatePreview
                :template="current"
                mode="preview"
                :editable="true"
                chrome="phone"
              />
            </div>
          </div>
        </div>

        <div v-else class="grid flex-1 place-items-center px-6 text-center">
          <div class="max-w-xs">
            <div class="mx-auto grid size-11 place-items-center rounded-full bg-surface-green-2 text-ink-green-7">
              <span class="lucide-layout-template size-5" aria-hidden="true" />
            </div>
            <p class="mt-3 text-sm font-semibold text-ink-gray-8">Choose a template</p>
            <p class="mt-1 text-xs leading-relaxed text-ink-gray-5">
              The customer view, sample values, and send action open here.
            </p>
          </div>
        </div>
      </div>
      </template>
    </DeskSplit>

    <!-- Send Template Modal Dialog -->
    <Dialog
      :open="Boolean(sending)"
      title="Send WhatsApp Template"
      size="lg"
      @update:open="(open) => !open && (sending = null)"
    >
      <div v-if="sending" class="space-y-4 py-2 text-xs">
        <div class="rounded-xl border border-teal-200 bg-teal-50 p-3.5 text-ink-green-7 leading-relaxed">
          <p class="font-bold flex items-center gap-1.5">
            <span class="lucide-send size-4" /> Initiating Template Message
          </p>
          <p class="mt-1 text-ink-gray-7">
            Sending template <strong>{{ displayTitle(sending.template_label, sending.template_name) || 'Untitled template' }}</strong> ({{ sending.template_type }}). Templates can be delivered even when the customer's 24-hour service window is closed.
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

          <div class="max-h-48 overflow-y-auto divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2 bg-surface-base">
            <button
              v-for="r in filteredRecipients"
              :key="r.value"
              type="button"
              class="flex w-full items-center justify-between p-2.5 text-left transition-colors hover:bg-surface-gray-1"
              :class="recipient === r.value ? 'bg-teal-50/70 font-semibold text-ink-green-7' : 'text-ink-gray-8'"
              @click="recipient = r.value"
            >
              <div class="flex min-w-0 items-center gap-2">
                <span class="grid size-7 shrink-0 place-items-center rounded-full bg-teal-100 text-[10px] font-bold text-ink-green-7">
                  {{ initials(r.name) }}
                </span>
                <div class="min-w-0">
                  <p class="truncate text-xs">{{ r.name }}</p>
                  <p class="font-mono text-[11px] text-ink-gray-5">{{ r.phone }}</p>
                </div>
              </div>
              <span v-if="recipient === r.value" class="lucide-check size-4 shrink-0 text-ink-green-7" />
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
          <Button v-if="sending?.status === 'Approved'" variant="solid" theme="green" label="Confirm & Send Template" icon-left="lucide-send" :disabled="!recipient" :loading="desk.sending.value" @click="send"/>
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model="templateEditorOpen"
      :title="templateForm.name ? 'Edit template' : 'New template'"
      size="7xl"
      :dismissible="false"
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
            This template is already on Meta. Save draft keeps Nudg only; Submit updates Meta.
          </div>
          <p v-else class="text-ink-gray-6">
            Save a local draft first, then submit to Meta when the content is ready for review.
          </p>
          <p class="text-xs text-ink-gray-5">
            WhatsApp account: {{ displayTitle(selectedAccountLabel) || 'Select a number in the top bar' }}
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
              v-model="templateForm.language"
              type="select"
              label="Language"
              :options="languageOptions"
              :disabled="editorLocked || editorOnMeta || languagesLoading"
              :description="languagesLoading ? 'Loading languages…' : languageOptions.length ? undefined : 'No WA Language records on this site'"
            />
          </div>
          <FormControl
            v-model="templateForm.header_type"
            type="select"
            label="Header type"
            :options="headerTypeOptions"
            :disabled="editorLocked"
          />
          <FormControl
            v-if="templateForm.header_type === 'Text'"
            v-model="templateForm.header_text"
            type="text"
            label="Header text"
            :disabled="editorLocked"
          />
          <FileUploader
            v-else
            :file-types="headerFileTypes"
            :private="false"
            @success="onHeaderUploaded"
          >
            <template #default="{ uploading, progress, openFileSelector, error }">
              <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2">
                <div class="flex items-center justify-between gap-2">
                  <span class="font-medium text-ink-gray-7">Sample {{ templateForm.header_type.toLowerCase() }}</span>
                  <Button
                    size="sm"
                    variant="subtle"
                    :label="templateForm.header_media ? 'Replace' : 'Upload'"
                    :loading="uploading"
                    :disabled="editorLocked"
                    @click="openFileSelector"
                  />
                </div>
                <p v-if="uploading" class="mt-1 text-ink-gray-5">Uploading {{ progress }}%</p>
                <p v-else-if="templateForm.header_media" class="mt-1 truncate text-ink-gray-6">{{ headerFileLabel }}</p>
                <p v-else class="mt-1 text-ink-gray-5">
                  A draft can be saved without a file. Meta needs this sample before the template is submitted.
                </p>
                <Alert
                  v-if="error"
                  class="mt-2"
                  theme="red"
                  :title="error"
                  :primary-action="{ label: 'Try again', onClick: () => openFileSelector() }"
                />
              </div>
            </template>
          </FileUploader>
          <FormControl
            v-model="templateForm.message"
            type="textarea"
            label="Message"
            required
            :rows="4"
            :disabled="editorLocked"
          />
          <div
            v-if="detectedVariableNames.length"
            class="space-y-2 rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2"
          >
            <div>
              <p class="font-medium text-ink-gray-7">Variable examples</p>
              <p class="mt-0.5 text-ink-gray-5">
                Meta reviews the template with these values. The preview shows the same examples.
              </p>
            </div>
            <FormControl
              v-for="name in detectedVariableNames"
              :key="name"
              :model-value="variableExamples[name] || ''"
              type="text"
              :label="variableLabel(name)"
              placeholder="Example value"
              required
              :disabled="editorLocked"
              @update:model-value="setVariableExample(name, $event)"
            />
          </div>
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
            <span class="lucide-smartphone size-3.5 text-ink-green-7" />
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
            :loading="templateAction === 'delete'"
            :disabled="Boolean(templateAction)"
            @click="templateDeleteOpen = true"
          />
          <span v-else />
          <div class="flex flex-wrap gap-2">
            <Button variant="subtle" label="Cancel" :disabled="Boolean(templateAction)" @click="templateEditorOpen = false" />
            <Button
              variant="subtle"
              label="Save draft"
              loading-text="Saving…"
              :loading="templateAction === 'draft'"
              :disabled="Boolean(templateAction && templateAction !== 'draft') || Boolean(templateForm.name && !buttonsReady)"
              @click="persistTemplate(false)"
            />
            <Button
              variant="solid"
              theme="green"
              :label="editorOnMeta ? 'Update on Meta' : 'Submit to Meta'"
              loading-text="Saving…"
              :loading="templateAction === 'submit'"
              :disabled="Boolean(templateAction && templateAction !== 'submit') || Boolean(templateForm.name && !buttonsReady) || editorLocked"
              @click="persistTemplate(true)"
            />
          </div>
        </div>
      </template>
    </Dialog>

    <Dialog v-model="templateDeleteOpen" title="Delete template">
      <p class="text-sm text-ink-gray-7">
        Remove
        <strong>{{ displayTitle(templateForm.template_label) || 'Untitled template' }}</strong>
        from Nudg? Meta is unchanged until the next sync.
      </p>
      <template #actions>
        <div class="flex w-full justify-end gap-2">
          <Button variant="subtle" label="Cancel" :disabled="Boolean(templateAction)" @click="templateDeleteOpen = false" />
          <Button variant="solid" theme="red" label="Delete" :loading="templateAction === 'delete'" :disabled="Boolean(templateAction && templateAction !== 'delete')" @click="removeTemplate" />
        </div>
      </template>
    </Dialog>
  </DeskPage>
</template>

<style scoped>
.template-search {
  flex: 1 1 10rem !important;
  min-width: 8rem !important;
}
</style>
