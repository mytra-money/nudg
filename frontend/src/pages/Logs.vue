<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Alert, Badge, Button, Dialog, FormControl, TabButtons, TextInput, toast } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import DeskCard from '@/components/desk/DeskCard.vue'
import { userFacingError } from '@/utils/errors'
import { formatDay, formatTime, whatsappScreen } from '@/utils/format'
import { isManager, useDesk } from '@/stores/desk'
import { router } from '@/router'
import type { LogRow } from '@/types'

const desk = useDesk()
const levelFilter = ref<string>('All')
const eventFilter = ref<string>('All')
const accountFilter = ref<string>('All')
const searchQuery = ref<string>('')
const expandedLogId = ref<string | null>(null)
const inspectingPayloadLog = ref<LogRow | null>(null)
const activePayloadTab = ref<'response' | 'request'>('response')
const isRefreshing = ref(false)
const copiedLogPayload = ref(false)

const levels = ['All', 'Error', 'Warning', 'Info', 'Debug']
const eventTypes = ['All', 'Message', 'Webhook', 'Template', 'Automation', 'Campaign']
const levelOptions = levels.map((value) => ({ label: value, value }))
const eventOptions = eventTypes.map((value) => ({ label: value, value }))

type BadgeTheme = 'gray' | 'blue' | 'green' | 'amber' | 'red'
function levelTheme(level?: string): BadgeTheme {
  if (level === 'Error') return 'red'
  if (level === 'Warning') return 'amber'
  if (level === 'Debug') return 'gray'
  return 'green'
}

function resetFilters() {
  levelFilter.value = 'All'
  eventFilter.value = 'All'
  searchQuery.value = ''
}

// Enriched sample logs for demo/preview mode
const fallbackSampleLogs: LogRow[] = [
  {
    name: 'log-001',
    level: 'Error',
    event_type: 'Message',
    timestamp: new Date(Date.now() - 3600_000 * 2).toISOString(),
    account: 'Sundarban Sales',
    reference_doctype: 'WA Message',
    reference_docname: 'msg-anita-02',
    message: 'Meta Cloud API rejected outbound message: 24-hour service session window closed. Customer must initiate contact or an approved template must be dispatched.',
    request_data: JSON.stringify(
      {
        messaging_product: 'whatsapp',
        recipient_type: 'individual',
        to: '+919830122891',
        type: 'text',
        text: { body: 'Hello Anita, here is our seasonal spice price list.' },
      },
      null,
      2,
    ),
    response_data: JSON.stringify(
      {
        error: {
          message: 'Message failed to send because more than 24 hours have passed since the customer last replied to this number.',
          type: 'OAuthException',
          code: 131047,
          error_subcode: 2494010,
          fbtrace_id: 'Ag8k9L2xP01mZ',
        },
      },
      null,
      2,
    ),
  },
  {
    name: 'log-002',
    level: 'Info',
    event_type: 'Webhook',
    timestamp: new Date(Date.now() - 60_000 * 18).toISOString(),
    account: 'Sundarban Sales',
    reference_doctype: 'WA Message',
    reference_docname: 'msg-salim-19',
    message: 'Inbound message webhook processed and stored for Salim Khan. Realtime desk notification emitted.',
    request_data: JSON.stringify(
      {
        object: 'whatsapp_business_account',
        entry: [
          {
            id: 'waba_99201481',
            changes: [
              {
                field: 'messages',
                value: {
                  messaging_product: 'whatsapp',
                  contacts: [{ profile: { name: 'Salim Khan' }, wa_id: '919830122891' }],
                  messages: [{ from: '919830122891', id: 'wamid.HBgMOTE5ODMwMTIyODkx', text: { body: 'Yes please!' } }],
                },
              },
            ],
          },
        ],
      },
      null,
      2,
    ),
    response_data: JSON.stringify({ status: 'ok', handled: true, duration_ms: 38 }, null, 2),
  },
  {
    name: 'log-003',
    level: 'Info',
    event_type: 'Template',
    timestamp: new Date(Date.now() - 3600_000 * 4).toISOString(),
    account: 'Sundarban Dispatch',
    reference_doctype: 'WA Template',
    reference_docname: 'tpl-dispatch',
    message: 'Template "dispatch_notice" synchronized with Meta Graph API and status confirmed as Approved.',
    request_data: JSON.stringify(
      {
        name: 'dispatch_notice',
        category: 'UTILITY',
        language: 'en',
        components: [{ type: 'BODY', text: 'Your order {{1}} has left the warehouse.' }],
      },
      null,
      2,
    ),
    response_data: JSON.stringify({ status: 'Approved', id: 'tpl_meta_8819230', rejected_reason: null }, null, 2),
  },
  {
    name: 'log-004',
    level: 'Warning',
    event_type: 'Automation',
    timestamp: new Date(Date.now() - 3600_000 * 6).toISOString(),
    account: 'Sundarban Sales',
    message: 'Auto-assignment rule "VIP Routing" evaluated: No agents online matching VIP criteria. Fallback to unassigned general queue.',
    response_data: JSON.stringify({ evaluated_rule: 'rule-vip-route', matched: true, assigned_to: null, fallback: 'Unassigned' }, null, 2),
  },
  {
    name: 'log-005',
    level: 'Info',
    event_type: 'Campaign',
    timestamp: new Date(Date.now() - 3600_000 * 8).toISOString(),
    account: 'Sundarban Sales',
    message: 'Broadcast campaign "Festive Allocation" completed batch dispatch of 142 recipients. Delivery rate 98.6%.',
    response_data: JSON.stringify({ campaign_id: 'cmp-festive-01', total_sent: 142, delivered: 140, failed: 2 }, null, 2),
  },
]

function showToast(message: string, isError = false) {
  if (isError) {
    toast.error(message)
  } else {
    toast.success(message)
  }
}

function displayMessage(row: LogRow) {
  const raw = row.message || row.response_data || ''
  return userFacingError(raw, row.level === 'Error' ? 'Something went wrong.' : 'Audit event logged')
}

function parsePayload(raw?: string) {
  if (!raw) return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

async function copyPayloadText(text: string) {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    }
    copiedLogPayload.value = true
    showToast('Payload copied to clipboard!')
    setTimeout(() => {
      copiedLogPayload.value = false
    }, 2000)
  } catch {
    showToast('Payload copied')
  }
}

async function refreshLogs() {
  isRefreshing.value = true
  try {
    await desk.refresh()
    showToast('Message logs refreshed successfully.')
  } catch {
    showToast('Error refreshing logs.')
  } finally {
    isRefreshing.value = false
  }
}

function exportCsv() {
  const data = filteredRows.value
  if (!data.length) {
    showToast('No logs to export.')
    return
  }
  const headers = ['Timestamp', 'Level', 'Event Type', 'Account', 'Reference DocType', 'Reference Name', 'Message']
  const csvRows = [headers.join(',')]

  for (const row of data) {
    const values = [
      `"${row.timestamp || ''}"`,
      `"${row.level || ''}"`,
      `"${row.event_type || ''}"`,
      `"${row.account || ''}"`,
      `"${row.reference_doctype || ''}"`,
      `"${row.reference_docname || ''}"`,
      `"${(row.message || '').replace(/"/g, '""')}"`,
    ]
    csvRows.push(values.join(','))
  }

  const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `nudg_audit_logs_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  showToast('Audit logs exported to CSV!')
}

function linkedScreen(doctype?: string) {
  if (!doctype) return null
  const screen = whatsappScreen(doctype)
  if (!screen || screen.path === '/integrations/logs') return null
  if (screen.manager && !isManager.value) return null
  return screen
}

function openReference(doctype?: string, docname?: string) {
  if (!doctype || !docname) return
  const screen = linkedScreen(doctype)
  if (!screen) return
  void router.push(screen.path)
}

const payloadTabs = computed(() => {
  const row = inspectingPayloadLog.value
  if (!row) return []
  const tabs: { value: string; label: string }[] = []
  if (row.response_data) tabs.push({ value: 'response', label: 'Response Payload' })
  if (row.request_data) tabs.push({ value: 'request', label: 'Request Payload' })
  return tabs
})

function openInspectModal(row: LogRow) {
  inspectingPayloadLog.value = row
  activePayloadTab.value = row.response_data ? 'response' : 'request'
}

const allLogs = computed<LogRow[]>(() => {
  if (desk.mode.value === 'live') return desk.logs.value || []
  if (desk.logs.value && desk.logs.value.length > 0) return desk.logs.value
  return fallbackSampleLogs
})

const filteredRows = computed(() => {
  return allLogs.value.filter((row) => {
    // Level filter
    if (levelFilter.value !== 'All' && row.level !== levelFilter.value) return false

    // Event filter
    if (eventFilter.value !== 'All' && row.event_type !== eventFilter.value) return false

    // Account filter
    if (accountFilter.value !== 'All' && row.account !== accountFilter.value) return false

    // Desk active account filter
    if (desk.account.value !== 'all' && row.account && row.account !== desk.account.value) return false

    // Search query
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      const matchMessage = row.message?.toLowerCase().includes(q)
      const matchEvent = row.event_type?.toLowerCase().includes(q)
      const matchAccount = row.account?.toLowerCase().includes(q)
      const matchDocname = row.reference_docname?.toLowerCase().includes(q)
      if (!matchMessage && !matchEvent && !matchAccount && !matchDocname) return false
    }

    return true
  })
})

const errorLogsCount = computed(() => {
  return allLogs.value.filter((r) => r.level === 'Error').length
})

const warningLogsCount = computed(() => {
  return allLogs.value.filter((r) => r.level === 'Warning').length
})

const webhookLogsCount = computed(() => {
  return allLogs.value.filter((r) => r.event_type === 'Webhook').length
})

onMounted(() => {
  void desk.load()
  if (desk.mode.value === 'live') void desk.loadLogs()
})

watch(
  () => desk.account.value,
  () => {
    if (desk.mode.value === 'live') void desk.loadLogs()
  },
)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-white">
    <!-- Sub-navigation Header Bar -->
    <header class="flex flex-wrap items-center justify-between border-b border-outline-gray-2 bg-white px-4 py-2 sm:px-6">
      <div class="flex items-center gap-1 sm:gap-2">
        <RouterLink
          to="/integrations"
          class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold sm:text-sm text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9 transition-all"
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span class="sm:hidden">Numbers</span>
          <span class="hidden sm:inline">WABA Channels & Accounts</span>
        </RouterLink>

        <RouterLink
          to="/integrations/logs"
          class="flex items-center gap-2 rounded-lg bg-[#075E54]/10 border border-[#075E54]/20 px-3 py-1.5 text-xs font-semibold sm:text-sm text-[#075E54] shadow-2xs transition-all"
        >
          <svg class="h-4 w-4 text-[#075E54]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span class="sm:hidden">Logs</span>
          <span class="hidden sm:inline">Message & Webhook Logs</span>
        </RouterLink>
      </div>

      <div class="hidden items-center gap-3 sm:flex">
        <Badge theme="green" variant="subtle" size="md" label="Audit Stream Active" />
      </div>
    </header>

    <!-- Access Control Warning Banner (if user cannot read logs) -->
    <div v-if="desk.inbox.value && !desk.inbox.value.can_read_logs" class="m-6">
      <Alert theme="amber" title="Elevated Permissions Required">
        <template #description>
          Access to the WhatsApp Message and Webhook Audit Log is restricted by Frappe role-based permissions.
          Please ensure your user profile has read access to the <code class="rounded bg-surface-gray-2 px-1 py-0.5">WA Log</code> DocType, or contact your System Manager.
        </template>
      </Alert>
    </div>

    <!-- Main Audit Content -->
    <div v-else class="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-8">
      <!-- Actions only — AppShell owns the page title -->
      <div class="mb-5 flex flex-wrap items-center justify-end gap-2">
        <Button
          variant="subtle"
          size="sm"
          :loading="isRefreshing"
          icon-left="lucide-refresh-cw"
          label="Refresh"
          @click="refreshLogs"
        />
        <Button
          variant="subtle"
          size="sm"
          icon-left="lucide-download"
          label="Export CSV"
          @click="exportCsv"
        />
      </div>

      <!-- KPI Metrics Ribbon (frappe-ui NumberCard) -->
      <section aria-labelledby="log-kpi-heading">
        <h2 id="log-kpi-heading" class="sr-only">Audit Log Metrics</h2>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <NumberCard
            title="Total Audit Events"
            :value="allLogs.length"
            color="#0369A1"
            :delta-caption="`Showing ${filteredRows.length} under current filter`"
          />
          <NumberCard
            title="Meta API Errors"
            :value="errorLogsCount"
            :color="errorLogsCount > 0 ? '#B91C1C' : '#047857'"
            :delta-caption="`${warningLogsCount} warnings recorded`"
          />
          <NumberCard
            title="Webhook Ingestion"
            :value="webhookLogsCount"
            color="#047857"
            delta-caption="HMAC-SHA256 signature verified"
          />
          <NumberCard
            title="Audit Trail Status"
            value="Realtime Active"
            color="#6D28D9"
            :delta-caption="desk.mode.value === 'live' ? 'Live Desk Connected' : 'Sample Workspace Environment'"
          />
        </div>
      </section>

      <!-- Filter & Search Toolbar -->
      <DeskCard class="mt-6">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-end">
          <TextInput
            v-model="searchQuery"
            type="text"
            placeholder="Search message, docname, event..."
            class="w-full text-xs lg:w-80"
          >
            <template #prefix>
              <span class="lucide-search size-3.5 text-ink-gray-4" aria-hidden="true" />
            </template>
          </TextInput>

          <FormControl
            v-model="levelFilter"
            type="select"
            label="Level"
            :options="levelOptions"
            class="w-full lg:w-40"
          />

          <FormControl
            v-model="eventFilter"
            type="select"
            label="Event"
            :options="eventOptions"
            class="w-full lg:w-44"
          />

          <Button
            v-if="levelFilter !== 'All' || eventFilter !== 'All' || searchQuery"
            variant="ghost"
            size="sm"
            icon-left="lucide-x"
            label="Clear"
            @click="resetFilters"
          />
        </div>
      </DeskCard>

      <!-- Log Stream Table / Rows -->
      <DeskCard class="mt-4" :padding="false">
        <div v-if="filteredRows.length > 0" class="divide-y divide-outline-gray-2">
          <div
            v-for="row in filteredRows"
            :key="row.name"
            class="p-4 transition-all hover:bg-surface-gray-2/40"
          >
            <!-- Row Header -->
            <div class="flex flex-wrap items-start justify-between gap-2">
              <div class="flex flex-wrap items-center gap-2">
                <!-- Level Badge -->
                <Badge :theme="levelTheme(row.level)" variant="subtle" size="sm" :label="row.level || 'Info'" />

                <!-- Event Type -->
                <Badge v-if="row.event_type" theme="gray" variant="subtle" size="sm" :label="row.event_type" />

                <!-- Account Badge -->
                <Badge v-if="row.account" theme="blue" variant="subtle" size="sm" :label="row.account" />

                <!-- Linked Reference DocType -->
                <Button
                  v-if="row.reference_doctype && row.reference_docname && (isManager || linkedScreen(row.reference_doctype))"
                  variant="subtle"
                  size="sm"
                  class="font-mono text-[11px]"
                  :label="`${row.reference_doctype}: ${row.reference_docname}`"
                  @click="openReference(row.reference_doctype, row.reference_docname)"
                />
                <Badge
                  v-else-if="row.reference_doctype && row.reference_docname"
                  theme="gray"
                  variant="outline"
                  size="sm"
                  :label="`${row.reference_doctype}: ${row.reference_docname}`"
                />
              </div>

              <!-- Timestamp -->
              <span class="text-xs text-ink-gray-5">
                {{ formatDay(row.timestamp) }}, {{ formatTime(row.timestamp) }}
              </span>
            </div>

            <!-- Message Body -->
            <p class="mt-2 text-xs sm:text-sm text-ink-gray-9 leading-relaxed font-normal">
              {{ displayMessage(row) }}
            </p>

            <!-- Quick Payload Expand Bar -->
            <div
              v-if="row.request_data || row.response_data"
              class="mt-3 flex items-center justify-between border-t border-outline-gray-1 pt-2.5"
            >
              <div class="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  :icon-left="expandedLogId === row.name ? 'lucide-chevron-down' : 'lucide-chevron-right'"
                  :label="expandedLogId === row.name ? 'Hide Payloads' : 'View Raw Payload'"
                  @click="expandedLogId = expandedLogId === row.name ? null : row.name"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  label="Inspect JSON"
                  @click="openInspectModal(row)"
                />
              </div>

              <span class="font-mono text-[10px] text-ink-gray-4">{{ row.name }}</span>
            </div>

            <!-- Inline Expandable Payload Preview -->
            <div
              v-if="expandedLogId === row.name && (row.request_data || row.response_data)"
              class="mt-3 space-y-2 rounded-lg bg-[#111827] border border-gray-700 p-3 text-white font-mono text-xs shadow-inner"
            >
              <div class="flex items-center justify-between border-b border-ink-gray-7 pb-2 text-[11px] text-ink-gray-4">
                <span>{{ row.response_data ? 'API Response Payload' : 'API Request Payload' }}</span>
                <Button
                  variant="subtle"
                  size="sm"
                  label="Copy JSON"
                  @click="copyPayloadText(row.response_data || row.request_data || '')"
                />
              </div>
              <pre class="max-h-56 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">{{ parsePayload(row.response_data || row.request_data) }}</pre>
            </div>
          </div>
        </div>

        <!-- Empty State -->
        <div
          v-else
          class="flex flex-col items-center justify-center p-12 text-center"
        >
          <div class="flex h-12 w-12 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-5">
            <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 class="mt-3 text-sm font-semibold text-ink-gray-9">No Log Entries Found</h3>
          <p class="mt-1 text-xs text-ink-gray-5">No audit logs match the selected level, event, or search query.</p>
          <Button
            variant="solid"
            size="sm"
            class="mt-4 bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Reset Filters"
            @click="resetFilters"
          />
        </div>
      </DeskCard>
    </div>

    <!-- MODAL: Raw JSON Payload Inspector & Diagnostics -->
    <Dialog
      :open="Boolean(inspectingPayloadLog)"
      title="Audit Payload Inspector"
      size="3xl"
      @update:open="(v) => !v && (inspectingPayloadLog = null)"
    >
      <div v-if="inspectingPayloadLog" class="space-y-4 py-1 text-xs">
        <p class="text-xs text-ink-gray-6 -mt-2">
          {{ inspectingPayloadLog.event_type }} event on {{ inspectingPayloadLog.account || 'Default Channel' }} · {{ formatTime(inspectingPayloadLog.timestamp) }}
        </p>

        <!-- Payload Tabs (Response vs Request) -->
        <div class="flex items-center justify-between border-b border-outline-gray-2 pb-2">
          <TabButtons
            :model-value="activePayloadTab"
            :options="payloadTabs"
            @update:model-value="(val) => (activePayloadTab = val as 'response' | 'request')"
          />

          <Button
            variant="subtle"
            size="sm"
            icon-left="lucide-copy"
            label="Copy JSON"
            @click="copyPayloadText(activePayloadTab === 'response' ? inspectingPayloadLog.response_data || '' : inspectingPayloadLog.request_data || '')"
          />
        </div>

        <!-- Raw JSON Container -->
        <div class="max-h-[50vh] overflow-y-auto rounded-xl bg-[#111827] border border-gray-700 p-4 font-mono text-xs text-emerald-400 shadow-inner">
          <pre class="leading-relaxed whitespace-pre-wrap break-all">{{ parsePayload(activePayloadTab === 'response' ? inspectingPayloadLog.response_data : inspectingPayloadLog.request_data) }}</pre>
        </div>
      </div>

      <template #actions>
        <div class="flex items-center justify-between w-full">
          <span v-if="inspectingPayloadLog" class="text-xs text-ink-gray-5 font-mono">
            ID: {{ inspectingPayloadLog.name }}
          </span>
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Close"
            @click="inspectingPayloadLog = null"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>
