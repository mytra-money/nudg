<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, Combobox, Password, Select, TextInput, call, Dialog, toast } from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import WhatsAppTemplatePreview from '@/components/templates/WhatsAppTemplatePreview.vue'
import { errorText } from '@/utils/format'
import { displayTitle } from '@/utils/titles'
import { userFacingError } from '@/utils/errors'
import { fallbackSample } from '@/utils/templatePreview'
import { useDesk } from '@/stores/desk'
import type { Template } from '@/types'

const LIST_LIMIT = 10

const desk = useDesk()
const live = computed(() => Boolean(window.csrf_token))
const loading = ref(true)
const error = ref<string | null>(null)
const busy = ref(false)
const sites = ref<any[]>([])
const accounts = computed(() => desk.inbox.value?.accounts || [])
const alerts = ref<Record<string, any[]>>({})
const alertErrors = ref<Record<string, string>>({})
const alertsLoading = ref<Record<string, boolean>>({})
const confirmDelete = ref('')
const verifyOpen = ref(false)
const verifyOk = ref(false)
const verifyReason = ref('')
const verifyChecks = ref<{ name: string; ok: boolean; detail: string }[]>([])

const siteForm = ref({
  site_name: '',
  site_url: '',
  api_key: '',
  api_secret: '',
  whatsapp_account: '',
})

const alertOpen = ref(false)
const alertSite = ref<any>(null)
const editing = ref<any>(null)
const alertSaving = ref(false)
const doctypeQuery = ref('')
const doctypeResults = ref<any[]>([])
const doctypeLoading = ref(false)
const phoneQuery = ref('')
const variableQueries = ref<Record<string, string>>({})
const showPreview = ref(false)
const alertVisible = ref<Record<string, number>>({})
const siteLimit = ref(LIST_LIMIT)
const accountQuery = ref('')
const templateQuery = ref('')
const described = ref<any>(null)
const searchError = ref('')
const describeError = ref('')
const templates = ref<any[]>([])
const templateError = ref('')
const alertForm = ref({
  doctype: '',
  event: '',
  phone_field: '',
  template: '',
  variableMap: {} as Record<string, string>,
})
let searchToken = 0
let searchTimer: ReturnType<typeof setTimeout> | null = null

function cleanUrl(value: string | undefined) {
  return (value || '').trim().replace(/\/+$/, '')
}

function accountLabel(site: { whatsapp_account?: string }) {
  const match = accounts.value.find((row: { name: string; account_name?: string }) => row.name === site.whatsapp_account)
  return match?.account_name || site.whatsapp_account || ''
}

function siteTitle(site: { site_name?: string; site_url?: string; whatsapp_account?: string }) {
  const name = (site.site_name || '').trim()
  if (name && cleanUrl(name) !== cleanUrl(site.site_url)) return name
  return accountLabel(site)
}

function siteDetail(site: { site_name?: string; site_url?: string; status?: string; whatsapp_account?: string }) {
  const account = accountLabel(site)
  const parts = [cleanUrl(site.site_url), site.status || 'Pending']
  if (siteTitle(site) !== account && account) parts.push(account)
  return parts.filter(Boolean).join(' · ')
}

const eventLabels: Record<string, string> = {
  after_insert: 'After create',
  on_update: 'After save',
  on_submit: 'On submit',
  on_cancel: 'On cancel',
}

const selectedTemplate = computed(() => templates.value.find((row) => row.name === alertForm.value.template))
const templateVariables = computed(() =>
  (selectedTemplate.value?.variables || []).map((row: { name: string; example?: string } | string) =>
    typeof row === 'string' ? { name: row, example: '' } : row,
  ),
)
const visibleSites = computed(() => sites.value.slice(0, siteLimit.value))
const accountOptions = computed(() =>
  limitedOptions(
    accounts.value,
    accountQuery.value,
    siteForm.value.whatsapp_account,
    (row: { name: string; account_name?: string }) => displayTitle(row.account_name) || 'WhatsApp account',
  ),
)
const doctypeOptions = computed(() => {
  const options = doctypeResults.value.slice(0, LIST_LIMIT).map((row) => ({
    label: row.name,
    value: row.name,
    description: row.description,
  }))
  if (alertForm.value.doctype && !options.some((row) => row.value === alertForm.value.doctype)) {
    options.unshift({ label: alertForm.value.doctype, value: alertForm.value.doctype, description: '' })
  }
  return options
})
const eventOptions = computed(() =>
  (described.value?.events || []).map((event: string) => ({ label: eventLabel(event), value: event })),
)
const templateOptions = computed(() =>
  limitedOptions(
    templates.value,
    templateQuery.value,
    alertForm.value.template,
    (row: { name: string; label?: string }) => displayTitle(row.label) || 'Template',
  ),
)
function alertTemplate(name?: string) {
  const row = templates.value.find((item) => item.name === name)
  return displayTitle(row?.label) || 'Template'
}

const previewTemplate = computed<Template | null>(() => {
  const row = selectedTemplate.value
  if (!row?.message) return null
  return {
    name: row.name,
    template_label: displayTitle(row.label) || 'Template',
    template_name: row.template_name,
    template_type: '',
    language: '',
    status: 'Approved',
    message: row.message,
    header_text: row.header_text || '',
    header_type: row.header_type || 'Text',
    footer: row.footer || '',
    buttons: [],
    whatsapp_account: accountLabel(alertSite.value || {}),
    template_variables: templateVariables.value.map((variable: { name: string; example?: string }) => ({
      variable_name: variable.name,
      variable_example: variable.example || '',
    })),
  }
})
const previewSamples = computed(() => {
  const values: Record<string, string> = {}
  for (const variable of templateVariables.value) {
    const fieldname = alertForm.value.variableMap[variable.name]
    const field = (described.value?.fields || []).find((row: { fieldname: string }) => row.fieldname === fieldname)
    values[variable.name] =
      described.value?.sample?.[fieldname] || field?.label || variable.example || fallbackSample(variable.name)
  }
  return values
})

async function load() {
  if (!live.value) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = null
  try {
    sites.value = (await call<any[]>('nudg.integrations.erpnext.api.list_sites')) || []
    if (!siteForm.value.whatsapp_account && accounts.value.length) {
      siteForm.value.whatsapp_account = accounts.value[0].name
    }
  } catch (err) {
    error.value = errorText(err)
  } finally {
    loading.value = false
  }
  await Promise.all(sites.value.map((site) => loadAlerts(site)))
}

async function loadAlerts(site: any) {
  alertsLoading.value = { ...alertsLoading.value, [site.name]: true }
  try {
    const rows = (await call<any[]>('nudg.integrations.erpnext.api.list_alerts', { site: site.name })) || []
    alerts.value = { ...alerts.value, [site.name]: rows }
    alertErrors.value = { ...alertErrors.value, [site.name]: '' }
  } catch (err) {
    alertErrors.value = { ...alertErrors.value, [site.name]: errorText(err) }
  } finally {
    alertsLoading.value = { ...alertsLoading.value, [site.name]: false }
  }
}

async function connect() {
  busy.value = true
  try {
    const result = await call<any>('nudg.integrations.erpnext.api.connect_site', { ...siteForm.value })
    siteForm.value.api_key = ''
    siteForm.value.api_secret = ''
    await load()
    verifyOk.value = Boolean(result?.ok) && result?.status !== 'Error'
    verifyChecks.value = Array.isArray(result?.checks) ? result.checks : []
    if (verifyOk.value) {
      const user = result?.remote_user ? ` Signed in as ${result.remote_user}.` : ''
      verifyReason.value = `Everything is fine.${user} WhatsApp is installed on that site and this user has the permissions Nudg needs. Site status is Connected.`
    } else {
      verifyReason.value = result?.reason || result?.last_error || 'The site could not be verified.'
    }
    verifyOpen.value = true
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busy.value = false
  }
}

async function toggleSite(site: any) {
  busy.value = true
  try {
    await call('nudg.integrations.erpnext.api.set_site_enabled', {
      site: site.name,
      enabled: site.status === 'Connected' ? 0 : 1,
    })
    await load()
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busy.value = false
  }
}

function resetAlertForm() {
  doctypeQuery.value = ''
  doctypeResults.value = []
  phoneQuery.value = ''
  variableQueries.value = {}
  showPreview.value = false
  described.value = null
  searchError.value = ''
  describeError.value = ''
  templateError.value = ''
  templateQuery.value = ''
  editing.value = null
  alertForm.value = { doctype: '', event: '', phone_field: '', template: '', variableMap: {} }
}

function closeAlert() {
  alertOpen.value = false
  editing.value = null
}

async function openAlert(site: any) {
  alertSite.value = site
  resetAlertForm()
  alertOpen.value = true
  templates.value = []
  try {
    templates.value = (await call<any[]>('nudg.integrations.erpnext.api.list_alert_templates', { site: site.name })) || []
  } catch (err) {
    templateError.value = errorText(err)
  }
}

function onDoctypeQuery(value: string) {
  const text = String(value || '')
  if (!text || text === alertForm.value.doctype) return
  doctypeQuery.value = text
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => searchDoctypes(), 250)
}

function limitedOptions<T extends { name: string }>(
  rows: T[],
  query: string,
  selected: string,
  labelOf: (row: T) => string,
) {
  const current = rows.find((row) => row.name === selected)
  const currentLabel = current ? labelOf(current) : ''
  const text = (query || '').trim().toLowerCase()
  const idle = !text || text === currentLabel.toLowerCase() || text === selected.toLowerCase()
  const matched = idle
    ? rows
    : rows.filter((row) => `${labelOf(row)} ${row.name}`.toLowerCase().includes(text))
  const visible = matched.slice(0, LIST_LIMIT)
  if (current && !visible.some((row) => row.name === current.name)) visible.unshift(current)
  return visible.map((row) => ({ label: labelOf(row), value: row.name }))
}

function fieldOptions(query: string, selected: string) {
  const fields = described.value?.fields || []
  const selectedField = fields.find((row: { fieldname: string }) => row.fieldname === selected)
  const selectedLabel = selectedField ? `${selectedField.label} (${selectedField.fieldname})` : ''
  const text = (query || '').trim().toLowerCase()
  const idle = !text || text === selectedLabel.toLowerCase() || text === selected.toLowerCase()
  const preferred = fields.filter(
    (row: { fieldname: string; fieldtype: string }) =>
      row.fieldtype === 'Phone' || /phone|mobile|contact/i.test(row.fieldname),
  )
  const rows = idle
    ? preferred.length
      ? preferred
      : fields
    : fields.filter((row: { label: string; fieldname: string }) =>
        `${row.label} ${row.fieldname}`.toLowerCase().includes(text),
      )
  const visible = rows.slice(0, LIST_LIMIT)
  if (selectedField && !visible.some((row: { fieldname: string }) => row.fieldname === selected)) {
    visible.unshift(selectedField)
  }
  return visible.map((row: { label: string; fieldname: string }) => ({
    label: `${row.label} (${row.fieldname})`,
    value: row.fieldname,
  }))
}

function visibleAlerts(site: { name: string }) {
  const rows = alerts.value[site.name] || []
  return rows.slice(0, alertVisible.value[site.name] || LIST_LIMIT)
}

function showMoreAlerts(site: { name: string }) {
  const current = alertVisible.value[site.name] || LIST_LIMIT
  alertVisible.value = { ...alertVisible.value, [site.name]: current + LIST_LIMIT }
}

async function searchDoctypes() {
  const site = alertSite.value
  if (!site) return
  const token = ++searchToken
  doctypeLoading.value = true
  try {
    const rows = await call<any[]>('nudg.integrations.erpnext.api.list_remote_doctypes', {
      site: site.name,
      query: doctypeQuery.value,
    })
    if (token === searchToken) {
      doctypeResults.value = rows || []
      searchError.value = ''
    }
  } catch (err) {
    if (token === searchToken) {
      doctypeResults.value = []
      searchError.value = errorText(err)
    }
  } finally {
    if (token === searchToken) doctypeLoading.value = false
  }
}

async function describeDoctype(name: string, preserve: boolean) {
  const site = alertSite.value
  if (!site) return
  const saved = { ...alertForm.value, variableMap: { ...alertForm.value.variableMap } }
  alertForm.value.doctype = name
  if (!preserve) {
    alertForm.value.event = ''
    alertForm.value.phone_field = ''
    alertForm.value.variableMap = Object.fromEntries(
      templateVariables.value.map((variable: { name: string }) => [variable.name, '']),
    )
  }
  described.value = null
  describeError.value = ''
  try {
    described.value = await call('nudg.integrations.erpnext.api.describe_remote_doctype', {
      site: site.name,
      doctype: name,
    })
    if (preserve) {
      alertForm.value.event = saved.event
      alertForm.value.phone_field = saved.phone_field
      alertForm.value.template = saved.template
      alertForm.value.variableMap = saved.variableMap
      return
    }
    const events = described.value?.events || []
    alertForm.value.event = events.includes('on_submit') ? 'on_submit' : events[0] || ''
  } catch (err) {
    describeError.value = errorText(err)
  }
}

function onDoctypePicked(value: string | number | null | undefined) {
  const name = String(value || '')
  if (!name || described.value?.name === name) return
  doctypeResults.value = []
  describeDoctype(name, false)
}

watch(
  () => alertForm.value.template,
  (name, previous) => {
    if (!previous || name === previous) return
    showPreview.value = false
    alertForm.value.variableMap = Object.fromEntries(
      templateVariables.value.map((variable: { name: string }) => [variable.name, '']),
    )
  },
)

async function openEdit(site: any, alert: any) {
  alertSite.value = site
  resetAlertForm()
  editing.value = alert
  alertForm.value = {
    doctype: alert.doctype,
    event: alert.event,
    phone_field: alert.phone_field,
    template: alert.template,
    variableMap: { ...(alert.variables || {}) },
  }
  alertOpen.value = true
  templates.value = []
  try {
    templates.value = (await call<any[]>('nudg.integrations.erpnext.api.list_alert_templates', { site: site.name })) || []
  } catch (err) {
    templateError.value = errorText(err)
  }
  await describeDoctype(alert.doctype, true)
}

async function saveAlert() {
  const site = alertSite.value
  if (!site) return
  if (!alertForm.value.doctype || !alertForm.value.event || !alertForm.value.phone_field || !alertForm.value.template) {
    toast.error('Choose the document type, event, phone field, and template.')
    return
  }
  const missing = templateVariables.value.filter((variable: { name: string }) => !alertForm.value.variableMap[variable.name])
  if (missing.length) {
    showPreview.value = true
    toast.error('Open the preview and map each template variable to a field.')
    return
  }
  alertSaving.value = true
  try {
    await call('nudg.integrations.erpnext.api.create_alert', {
      site: site.name,
      doctype: alertForm.value.doctype,
      event: alertForm.value.event,
      phone_field: alertForm.value.phone_field,
      template: alertForm.value.template,
      variable_map: alertForm.value.variableMap,
    })
    toast.success(editing.value ? 'Alert updated on the ERPNext site.' : 'Alert saved on the ERPNext site.')
    closeAlert()
    await loadAlerts(site)
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    alertSaving.value = false
  }
}

async function toggleAlert(site: any, alert: any) {
  busy.value = true
  try {
    await call('nudg.integrations.erpnext.api.set_alert_enabled', {
      site: site.name,
      alert: alert.name,
      enabled: alert.enabled ? 0 : 1,
    })
    await loadAlerts(site)
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busy.value = false
  }
}

async function removeAlert(site: any, alert: any) {
  if (confirmDelete.value !== alert.name) {
    confirmDelete.value = alert.name
    return
  }
  confirmDelete.value = ''
  busy.value = true
  try {
    await call('nudg.integrations.erpnext.api.delete_alert', { site: site.name, alert: alert.name })
    toast.success('Alert removed from the ERPNext site.')
    await loadAlerts(site)
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busy.value = false
  }
}

function eventLabel(event: string) {
  return eventLabels[event] || event
}

onMounted(load)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-white">
    <header class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 bg-white px-4 py-2 sm:px-6">
      <RouterLink to="/integrations" class="rounded-lg px-3 py-1.5 text-sm font-semibold text-ink-gray-6 hover:bg-surface-gray-2">WhatsApp numbers</RouterLink>
      <RouterLink to="/integrations/erpnext" class="rounded-lg border border-[#075E54]/20 bg-[#075E54]/10 px-3 py-1.5 text-sm font-semibold text-[#075E54]">ERPNext</RouterLink>
    </header>

    <div class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex max-w-3xl flex-col gap-6">
        <section class="rounded-xl border border-outline-gray-2 bg-white p-4">
          <p class="text-sm text-ink-gray-6">
            Connect an ERPNext site with its API key. Add an alert here and Nudg creates the Webhook on that site for the document and event you pick. When that event happens, their site calls Nudg and Nudg sends the WhatsApp template.
          </p>
        </section>

        <LoadingState v-if="loading" />
        <ErrorState v-else-if="error" :message="error" allow-retry @retry="load" />
        <EmptyState
          v-else-if="!visibleSites.length && !live"
          title="No ERPNext sites connected"
          description="Open Nudg on a signed-in site to connect ERPNext."
        />
        <section v-else class="rounded-xl border border-outline-gray-2 bg-white p-4">
          <h2 class="text-sm font-semibold text-ink-gray-9">Connect a site</h2>
          <p class="mt-1 text-sm text-ink-gray-6">
            Saving checks that this site is reachable, that WA Account, WA Profile, and WA Message are installed, and that this API user can use them. A failed check is shown so you can fix it. Site status becomes Connected after the checks pass, or Error when the site or API cannot be used.
          </p>
          <p v-if="!live" class="mt-2 text-sm text-ink-gray-6">Open Nudg on a signed-in site to connect ERPNext.</p>
          <form v-else class="mt-3 grid gap-3 sm:grid-cols-2" @submit.prevent="connect">
            <TextInput v-model="siteForm.site_name" label="Site name" placeholder="Acme" required />
            <TextInput v-model="siteForm.site_url" label="Site URL" placeholder="https://company.frappe.cloud" required />
            <TextInput v-model="siteForm.api_key" label="API key" placeholder="API key" required />
            <Password v-model="siteForm.api_secret" label="API secret" placeholder="API secret" required />
            <Combobox
              v-model="siteForm.whatsapp_account"
              v-model:query="accountQuery"
              label="WhatsApp account"
              placeholder="Search an account"
              :options="accountOptions"
              :filterable="false"
              empty-text="No matching account"
            />
            <div class="flex items-end">
              <Button variant="solid" :loading="busy" type="submit" label="Connect" />
            </div>
          </form>
          <p v-if="live && !sites.length" class="mt-4 text-sm text-ink-gray-6">No ERPNext sites connected yet.</p>
          <ul class="mt-4 divide-y divide-outline-gray-2">
            <li v-for="site in visibleSites" :key="site.name" class="py-3 text-sm">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div class="min-w-0">
                  <div class="font-medium text-ink-gray-9">{{ siteTitle(site) }}</div>
                  <div class="break-words text-ink-gray-6">{{ siteDetail(site) }}</div>
                  <div v-if="site.last_error" class="text-red-600">{{ userFacingError(site.last_error, 'This site could not connect.') }}</div>
                </div>
                <div class="flex flex-wrap gap-2">
                  <Button v-if="site.status === 'Connected'" variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" @click="openAlert(site)">Add alert</Button>
                  <Button variant="subtle" :loading="busy" @click="toggleSite(site)">{{ site.status === 'Connected' ? 'Disable' : 'Enable' }}</Button>
                </div>
              </div>
              <p v-if="alertsLoading[site.name]" class="mt-2 text-ink-gray-5">Loading alerts…</p>
              <p v-else-if="alertErrors[site.name]" class="mt-2 text-red-600">{{ alertErrors[site.name] }}</p>
              <ul v-else-if="alerts[site.name]?.length" class="mt-2 divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
                <li v-for="alert in visibleAlerts(site)" :key="alert.name" class="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <div class="min-w-0">
                    <div class="font-medium text-ink-gray-9">{{ alert.doctype }} · {{ eventLabel(alert.event) }}</div>
                    <div class="break-words text-ink-gray-6">{{ alertTemplate(alert.template) }} · {{ alert.phone_field }} · {{ alert.enabled ? 'On' : 'Off' }}</div>
                  </div>
                  <div class="flex flex-wrap gap-2">
                    <Button variant="subtle" :loading="busy" @click="openEdit(site, alert)">Edit</Button>
                    <Button variant="subtle" :loading="busy" @click="toggleAlert(site, alert)">{{ alert.enabled ? 'Turn off' : 'Turn on' }}</Button>
                    <Button variant="subtle" :loading="busy" @click="removeAlert(site, alert)">{{ confirmDelete === alert.name ? 'Confirm delete' : 'Delete' }}</Button>
                  </div>
                </li>
              </ul>
              <Button
                v-if="!alertsLoading[site.name] && !alertErrors[site.name] && (alerts[site.name]?.length || 0) > visibleAlerts(site).length"
                class="mt-2"
                variant="subtle"
                :label="`Show ${Math.min(LIST_LIMIT, (alerts[site.name]?.length || 0) - visibleAlerts(site).length)} more`"
                @click="showMoreAlerts(site)"
              />
              <p v-if="!alertsLoading[site.name] && !alertErrors[site.name] && !alerts[site.name]?.length" class="mt-2 text-ink-gray-5">No alerts yet.</p>
            </li>
          </ul>
          <Button
            v-if="sites.length > visibleSites.length"
            class="mt-3"
            variant="subtle"
            :label="`Show ${Math.min(LIST_LIMIT, sites.length - visibleSites.length)} more sites`"
            @click="siteLimit += LIST_LIMIT"
          />
        </section>
      </div>
    </div>

    <Dialog v-model="verifyOpen" :title="verifyOk ? 'Site verified' : 'Could not verify this site'">
      <div class="space-y-3 py-1 text-sm">
        <p class="text-ink-gray-7">{{ verifyReason }}</p>
        <ul v-if="verifyChecks.length" class="space-y-2">
          <li v-for="check in verifyChecks" :key="check.name">
            <div :class="check.ok ? 'font-medium text-[#075E54]' : 'font-medium text-red-600'">{{ check.name }}</div>
            <div class="text-ink-gray-6">{{ check.detail }}</div>
          </li>
        </ul>
        <p v-if="verifyOk" class="text-ink-gray-6">Nudg can store chats on this site.</p>
        <p v-else class="text-ink-gray-6">Fix the items above on the client site, then connect again. Messages Nudg cannot deliver are kept here and sent when the site is back.</p>
      </div>
      <template #actions>
        <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Close" @click="verifyOpen = false" />
      </template>
    </Dialog>

    <Dialog v-model="alertOpen" :title="editing ? 'Edit alert' : 'Add alert'">
      <div class="max-h-[70vh] space-y-3 overflow-auto py-1 text-sm">
        <p class="text-ink-gray-6">
          <template v-if="editing">
            The document type and event stay as they were created. Change the phone field, template, or variable fields. Turn the alert on or off from the list.
          </template>
          <template v-else>
            Document types come from {{ alertSite?.site_name || 'the connected site' }}. Nudg saves one Webhook there for this action.
          </template>
        </p>
        <template v-if="editing">
          <p class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm text-ink-gray-8">
            {{ alertForm.doctype }} · {{ eventLabel(alertForm.event) }}
          </p>
        </template>
        <template v-else>
          <Combobox
            v-model="alertForm.doctype"
            label="Document type"
            placeholder="Search document types"
            :options="doctypeOptions"
            :loading="doctypeLoading"
            :filterable="false"
            empty-text="Type a name, such as Sales"
            @update:query="onDoctypeQuery"
            @update:model-value="onDoctypePicked"
          />
        </template>
        <p v-if="searchError" class="text-xs text-red-600">{{ searchError }}</p>
        <p v-if="describeError" class="text-xs text-red-600">{{ describeError }}</p>
        <Select
          v-if="!editing"
          v-model="alertForm.event"
          label="Event"
          :options="eventOptions"
          :disabled="!described"
        />
        <Combobox
          v-model="alertForm.phone_field"
          v-model:query="phoneQuery"
          label="Phone field"
          placeholder="Search a phone field"
          :options="fieldOptions(phoneQuery, alertForm.phone_field)"
          :filterable="false"
          :disabled="!described"
          empty-text="No matching field"
        />
        <p v-if="described && !described.fields?.length" class="text-xs text-ink-gray-5">This document type has no text field Nudg can use as a phone number.</p>
        <Combobox
          v-model="alertForm.template"
          v-model:query="templateQuery"
          label="WhatsApp template"
          placeholder="Search an approved template"
          :options="templateOptions"
          :filterable="false"
          empty-text="No matching template"
        />
        <p v-if="templateError" class="text-xs text-red-600">{{ templateError }}</p>
        <p v-else-if="!templates.length" class="text-xs text-ink-gray-5">Approve a WhatsApp template for this account before adding an alert.</p>
        <div v-if="alertForm.template" class="space-y-3">
          <Button
            variant="subtle"
            :label="showPreview ? 'Hide preview' : 'Preview message'"
            @click="showPreview = !showPreview"
          />
          <div v-if="showPreview" class="space-y-3 rounded-lg border border-outline-gray-2 p-3">
            <WhatsAppTemplatePreview v-if="previewTemplate" :template="previewTemplate" :sample-values="previewSamples" :editable="false" />
            <p v-else class="text-xs text-ink-gray-5">This template has no message text to preview.</p>
            <p class="text-xs text-ink-gray-6">Placeholders use a value from the latest document when that field has one. Otherwise they use the field name or the template sample.</p>
            <Combobox
              v-for="variable in templateVariables"
              :key="variable.name"
              v-model="alertForm.variableMap[variable.name]"
              v-model:query="variableQueries[variable.name]"
              :label="variable.name"
              placeholder="Search a field"
              :options="fieldOptions(variableQueries[variable.name] || '', alertForm.variableMap[variable.name] || '')"
              :filterable="false"
              :disabled="!described"
              empty-text="No matching field"
            />
          </div>
        </div>
      </div>
      <template #actions>
        <div class="flex w-full items-center justify-end gap-2">
          <Button label="Cancel" @click="closeAlert" />
          <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" :label="editing ? 'Save changes' : 'Create alert'" :loading="alertSaving" @click="saveAlert" />
        </div>
      </template>
    </Dialog>
  </div>
</template>
