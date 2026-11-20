<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Badge, Button, Select, toast } from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { errorText, formatDay, formatTime } from '@/utils/format'
import { getAnalytics, refreshAnalytics } from '@/services/catalogApi'
import { isManager, useDesk } from '@/stores/desk'

const desk = useDesk()
const live = Boolean(window.csrf_token)

const loading = ref(true)
const error = ref<string | null>(null)
const latest = ref<any | null>(null)
const refreshing = ref<any | null>(null)
const history = ref<any[]>([])
const busy = ref(false)
const selectedAccount = ref('all')
let timer = 0

const sampleLatest = {
  name: 'snp-today',
  snapshot_date: new Date().toISOString().slice(0, 10),
  whatsapp_account: 'All Accounts',
  status: 'Ready',
  messages_in: 342,
  messages_out: 588,
  failed_messages: 6,
  open_conversations: 18,
  unassigned: 3,
  campaigns_sent: 4,
  generated_at: new Date(Date.now() - 60000 * 14).toISOString(),
}

const sampleHistory = [
  {
    name: 'snp-today',
    snapshot_date: new Date().toISOString().slice(0, 10),
    status: 'Ready',
    messages_in: 342,
    messages_out: 588,
    failed_messages: 6,
    open_conversations: 18,
    unassigned: 3,
    campaigns_sent: 4,
  },
  {
    name: 'snp-yesterday',
    snapshot_date: new Date(Date.now() - 86400000).toISOString().slice(0, 10),
    status: 'Ready',
    messages_in: 310,
    messages_out: 520,
    failed_messages: 4,
    open_conversations: 15,
    unassigned: 2,
    campaigns_sent: 2,
  },
  {
    name: 'snp-2days',
    snapshot_date: new Date(Date.now() - 86400000 * 2).toISOString().slice(0, 10),
    status: 'Ready',
    messages_in: 285,
    messages_out: 490,
    failed_messages: 3,
    open_conversations: 12,
    unassigned: 1,
    campaigns_sent: 1,
  },
  {
    name: 'snp-3days',
    snapshot_date: new Date(Date.now() - 86400000 * 3).toISOString().slice(0, 10),
    status: 'Ready',
    messages_in: 260,
    messages_out: 440,
    failed_messages: 2,
    open_conversations: 14,
    unassigned: 4,
    campaigns_sent: 3,
  },
]

const cards = computed(() => {
  const row = latest.value
  if (!row) return []
  return [
    {
      label: 'Incoming Inquiries',
      value: row.messages_in || 0,
      subtext: 'Customer inbound messages',
      pill: 'Inbound',
      theme: 'blue',
      icon: 'lucide-arrow-down-left',
    },
    {
      label: 'Outgoing Messages',
      value: row.messages_out || 0,
      subtext: 'Free-form & template sends',
      pill: 'Outbound',
      theme: 'teal',
      icon: 'lucide-arrow-up-right',
    },
    {
      label: 'Delivery Success Rate',
      value: `${deliveryRate.value}%`,
      subtext: `${row.failed_messages || 0} failed messages`,
      pill: row.failed_messages > 0 ? `${row.failed_messages} issues` : 'Optimal',
      theme: row.failed_messages > 0 ? 'amber' : 'green',
      icon: 'lucide-shield-check',
    },
    {
      label: 'Active 24h Sessions',
      value: row.open_conversations || 0,
      subtext: 'Live SLA customer care windows',
      pill: 'Meta Window',
      theme: 'green',
      icon: 'lucide-clock',
    },
    {
      label: 'Unassigned Queue',
      value: row.unassigned || 0,
      subtext: 'Awaiting team assignment',
      pill: row.unassigned > 0 ? 'Needs Attention' : 'Cleared',
      theme: row.unassigned > 0 ? 'red' : 'green',
      icon: 'lucide-users',
    },
    {
      label: 'Campaign Broadcasts',
      value: row.campaigns_sent || 0,
      subtext: 'Outbound marketing campaigns',
      pill: 'Broadcasts',
      theme: 'purple',
      icon: 'lucide-megaphone',
    },
  ]
})

const totalMessages = computed(() => {
  const row = latest.value
  if (!row) return 0
  return (row.messages_in || 0) + (row.messages_out || 0)
})

const inboundPercentage = computed(() => {
  if (totalMessages.value === 0) return 50
  return Math.round(((latest.value?.messages_in || 0) / totalMessages.value) * 100)
})

const outboundPercentage = computed(() => 100 - inboundPercentage.value)

const deliveryRate = computed(() => {
  const out = latest.value?.messages_out || 0
  const failed = latest.value?.failed_messages || 0
  if (out === 0) return 100
  return Math.max(0, Math.round(((out - failed) / out) * 100))
})

const linkedAccounts = computed(() => desk.inbox.value?.accounts || [])
const serverBlocked = ref(false)
const needsAccount = computed(() => live && (linkedAccounts.value.length === 0 || serverBlocked.value))

const accountOptions = computed(() => {
  return [
    { label: 'All Accounts', value: 'all' },
    ...linkedAccounts.value.map((a) => ({ label: a.account_name || a.name, value: a.name })),
  ]
})

async function load() {
  if (live && linkedAccounts.value.length === 0) {
    serverBlocked.value = false
    latest.value = null
    refreshing.value = null
    history.value = []
    error.value = null
    loading.value = false
    return
  }
  loading.value = !latest.value
  error.value = null
  try {
    if (!live) {
      latest.value = sampleLatest
      history.value = sampleHistory
      return
    }
    const accArg = selectedAccount.value === 'all' ? undefined : selectedAccount.value
    const payload = await getAnalytics(accArg)
    if (payload.has_accounts === false) {
      serverBlocked.value = true
      latest.value = null
      refreshing.value = null
      history.value = []
      return
    }
    serverBlocked.value = false
    latest.value = payload.latest || {
      messages_in: 0,
      messages_out: 0,
      failed_messages: 0,
      open_conversations: 0,
      unassigned: 0,
      campaigns_sent: 0,
      status: 'Ready',
    }
    refreshing.value = payload.refreshing
    history.value = payload.history || []
  } catch (caught) {
    if (!live) {
      latest.value = sampleLatest
      history.value = sampleHistory
    } else {
      error.value = errorText(caught)
    }
  } finally {
    loading.value = false
  }
}

async function refresh() {
  if (live && linkedAccounts.value.length === 0) return
  busy.value = true
  try {
    if (!live) {
      toast.success('Analytics snapshot refreshed (Simulation)')
      latest.value = {
        ...sampleLatest,
        generated_at: new Date().toISOString(),
      }
      return
    }
    const accArg = selectedAccount.value === 'all' ? undefined : selectedAccount.value
    await refreshAnalytics(accArg)
    toast.success('Analytics computation queued')
    await load()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    busy.value = false
  }
}

function exportCsv() {
  const headers = ['Snapshot Date', 'Status', 'Messages In', 'Messages Out', 'Failed', 'Open Conversations', 'Unassigned', 'Campaigns']
  const rows = history.value.map((h) => [
    `"${h.snapshot_date}"`,
    `"${h.status}"`,
    h.messages_in || 0,
    h.messages_out || 0,
    h.failed_messages || 0,
    h.open_conversations || 0,
    h.unassigned || 0,
    h.campaigns_sent || 0,
  ])
  const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n')
  const encodedUri = encodeURI(csvContent)
  const link = document.createElement('a')
  link.setAttribute('href', encodedUri)
  link.setAttribute('download', `whatsapp_analytics_${new Date().toISOString().slice(0, 10)}.csv`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  toast.success('Analytics history exported to CSV')
}

watch(
  () => linkedAccounts.value.map((row) => row.name).join(','),
  () => {
    if (selectedAccount.value !== 'all' && !linkedAccounts.value.some((row) => row.name === selectedAccount.value)) {
      selectedAccount.value = 'all'
    }
    void load()
  },
)

onMounted(() => {
  void load()
  timer = window.setInterval(() => {
    if (refreshing.value && !needsAccount.value) void load()
  }, 4000)
})

onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="flex h-full min-w-0 flex-col overflow-hidden bg-surface-gray-1">
    <!-- Top Action Header -->
    <header class="flex flex-col gap-3 border-b border-outline-gray-2 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between shrink-0">
      <div>
        <div class="flex items-center gap-2">
          <span class="rounded bg-[#075E54]/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-[#075E54]">
            Business Intelligence
          </span>
          <span class="text-xs text-ink-gray-5">·</span>
          <span class="text-xs font-medium text-ink-gray-6">Omnichannel Metric Snapshots</span>
        </div>
        <h1 class="mt-1 text-xl font-bold tracking-tight text-ink-gray-9">
          WhatsApp Analytics & SLA Health
        </h1>
      </div>

      <div v-if="!needsAccount" class="flex flex-wrap items-center gap-2">
        <Select
          class="w-36 text-xs"
          :model-value="selectedAccount"
          :options="accountOptions"
          @update:model-value="(val) => { selectedAccount = String(val || 'all'); load(); }"
        />
        <Button
          variant="subtle"
          size="sm"
          icon-left="lucide-download"
          label="Export CSV"
          @click="exportCsv"
        />
        <Button
          variant="solid"
          size="sm"
          class="bg-[#075E54] text-white hover:bg-[#128C7E]"
          icon-left="lucide-refresh-cw"
          label="Compute Snapshot"
          :loading="busy"
          @click="refresh"
        />
      </div>
    </header>

    <!-- Background Refresh Notification Banner -->
    <div
      v-if="refreshing"
      class="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800 shrink-0"
    >
      <span class="lucide-loader-2 size-3.5 animate-spin text-amber-600" />
      <span>
        Generating a new Metric Snapshot in background… displaying the latest Ready values until computation finishes.
      </span>
    </div>

    <!-- State Handlers -->
    <LoadingState v-if="loading && !latest && !needsAccount" label="Loading WhatsApp metrics…" />
    <ErrorState v-else-if="error" :message="error" allow-retry @retry="load" />
    <EmptyState
      v-else-if="needsAccount"
      title="No WhatsApp account linked"
      :description="isManager ? 'Connect a WhatsApp number before analytics can load. Numbers from other users stay hidden.' : 'No WhatsApp account is assigned to you yet. Ask a WhatsApp manager to link one before analytics can load.'"
    />
    <EmptyState
      v-else-if="!latest"
      title="No Analytics Snapshot Found"
      description="Click 'Compute Snapshot' to calculate and save your first Nudg metric record."
    >
      <Button
        variant="solid"
        class="mt-4 bg-[#075E54] text-white hover:bg-[#128C7E]"
        label="Compute First Snapshot"
        icon-left="lucide-refresh-cw"
        @click="refresh"
      />
    </EmptyState>

    <!-- Main Analytics Dashboard Canvas -->
    <div v-else class="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 space-y-6">
      <!-- Snapshot Status Bar -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs text-ink-gray-5 border-b border-outline-gray-2 pb-3">
        <div class="flex items-center gap-2">
          <span class="size-2 rounded-full bg-emerald-500" />
          <span>
            Snapshot Date: <strong class="text-ink-gray-8">{{ formatDay(latest.snapshot_date) }}</strong>
          </span>
          <span>·</span>
          <span>
            Generated: <strong class="text-ink-gray-8">{{ formatTime(latest.generated_at) }}</strong>
          </span>
        </div>
        <span class="font-mono text-[11px] text-ink-gray-4">Snapshot ID: {{ latest.name }}</span>
      </div>

      <!-- Hero KPI Grid (6 Cards) -->
      <section aria-labelledby="kpi-cards-heading">
        <h2 id="kpi-cards-heading" class="sr-only">Executive KPI Cards</h2>
        <div class="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <div
            v-for="card in cards"
            :key="card.label"
            class="rounded-xl border border-outline-gray-2 bg-white p-4.5 shadow-xs transition-all hover:border-[#128C7E] hover:shadow-sm"
          >
            <div class="flex items-start justify-between gap-2">
              <span class="min-w-0 text-xs font-medium uppercase tracking-wider text-ink-gray-6">
                {{ card.label }}
              </span>
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                :class="
                  card.theme === 'green'
                    ? 'bg-emerald-50 text-emerald-800'
                    : card.theme === 'teal'
                      ? 'bg-teal-50 text-[#075E54]'
                      : card.theme === 'blue'
                        ? 'bg-blue-50 text-blue-700'
                        : card.theme === 'red'
                          ? 'bg-red-50 text-red-700'
                          : card.theme === 'purple'
                            ? 'bg-purple-50 text-purple-700'
                            : 'bg-amber-50 text-amber-800'
                "
              >
                {{ card.pill }}
              </span>
            </div>

            <div class="mt-3 flex items-baseline gap-2">
              <span class="text-2xl font-semibold tracking-tight text-ink-gray-9 sm:text-3xl">
                {{ card.value }}
              </span>
            </div>

            <p class="mt-1 text-xs text-ink-gray-5">
              {{ card.subtext }}
            </p>
          </div>
        </div>
      </section>

      <!-- Traffic Ratio & Delivery Quality Panel (2-Column Grid) -->
      <section class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <!-- Card 1: Inbound vs Outbound Message Ratio -->
        <div class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-xs space-y-4">
          <div class="flex items-center justify-between border-b border-outline-gray-1 pb-3">
            <div>
              <h3 class="text-sm font-bold text-ink-gray-9">Traffic Volume Distribution</h3>
              <p class="text-xs text-ink-gray-5">Inbound customer queries vs outbound responses & templates</p>
            </div>
            <span class="text-xs font-semibold text-ink-gray-8">{{ totalMessages }} total</span>
          </div>

          <!-- Ratio Progress Bar -->
          <div class="space-y-2">
            <div class="flex h-3 w-full overflow-hidden rounded-full bg-surface-gray-2">
              <div
                class="bg-blue-600 transition-all duration-500"
                :style="`width: ${inboundPercentage}%`"
                title="Inbound Messages"
              />
              <div
                class="bg-[#075E54] transition-all duration-500"
                :style="`width: ${outboundPercentage}%`"
                title="Outbound Messages"
              />
            </div>

            <div class="flex justify-between text-xs pt-1">
              <div class="flex items-center gap-1.5">
                <span class="size-2 rounded-full bg-blue-600" />
                <span class="text-ink-gray-7">Inbound: <strong>{{ latest.messages_in }}</strong> ({{ inboundPercentage }}%)</span>
              </div>
              <div class="flex items-center gap-1.5">
                <span class="size-2 rounded-full bg-[#075E54]" />
                <span class="text-ink-gray-7">Outbound: <strong>{{ latest.messages_out }}</strong> ({{ outboundPercentage }}%)</span>
              </div>
            </div>
          </div>

          <p class="text-xs leading-relaxed text-ink-gray-6 bg-surface-gray-1/60 rounded-lg p-3">
            💡 Healthy omnichannel desks typically maintain a 1:1.5 to 1:2 ratio of inbound to outbound messages, reflecting prompt replies and automated notifications.
          </p>
        </div>

        <!-- Card 2: Meta 24-Hour SLA & Quality Rating -->
        <div class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-xs space-y-4">
          <div class="flex items-center justify-between border-b border-outline-gray-1 pb-3">
            <div>
              <h3 class="text-sm font-bold text-ink-gray-9">Meta SLA & Delivery Health</h3>
              <p class="text-xs text-ink-gray-5">Message delivery reliability and active service sessions</p>
            </div>
            <span class="rounded-full bg-emerald-100 text-emerald-800 px-2 py-0.5 text-xs font-semibold">
              High Quality
            </span>
          </div>

          <div class="grid grid-cols-2 gap-3 text-xs">
            <div class="rounded-lg border border-outline-gray-1 p-3 bg-surface-gray-1/40">
              <span class="text-ink-gray-5 block text-[11px] font-bold uppercase">Delivery Success</span>
              <p class="mt-1 text-2xl font-extrabold text-emerald-700">{{ deliveryRate }}%</p>
              <p class="mt-0.5 text-[11px] text-ink-gray-5">Carrier & Meta handoff rate</p>
            </div>
            <div class="rounded-lg border border-outline-gray-1 p-3 bg-surface-gray-1/40">
              <span class="text-ink-gray-5 block text-[11px] font-bold uppercase">SLA Window Sessions</span>
              <p class="mt-1 text-2xl font-extrabold text-[#075E54]">{{ latest.open_conversations }}</p>
              <p class="mt-0.5 text-[11px] text-ink-gray-5">Active customer care sessions</p>
            </div>
          </div>

          <p class="text-xs leading-relaxed text-ink-gray-6 bg-surface-gray-1/60 rounded-lg p-3">
            🛡️ <strong>Quality Rating:</strong> Keeping message failures under 2% protects your Meta WABA tier limits and ensures uninterrupted outbound broadcasting.
          </p>
        </div>
      </section>

      <!-- Snapshot History Table -->
      <section class="rounded-xl border border-outline-gray-2 bg-white shadow-xs overflow-hidden">
        <div class="flex items-center justify-between border-b border-outline-gray-2 p-4">
          <div>
            <h3 class="text-sm font-bold text-ink-gray-9">Snapshot Audit History</h3>
            <p class="text-xs text-ink-gray-5">Historical daily WhatsApp performance snapshots</p>
          </div>
          <span class="text-xs text-ink-gray-5">{{ history.length }} records</span>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs text-ink-gray-8">
            <thead class="border-b border-outline-gray-2 bg-surface-gray-1 text-[11px] font-bold uppercase tracking-wider text-ink-gray-5">
              <tr>
                <th scope="col" class="px-4 py-3">Date</th>
                <th scope="col" class="px-4 py-3">Status</th>
                <th scope="col" class="px-4 py-3">Inbound</th>
                <th scope="col" class="px-4 py-3">Outbound</th>
                <th scope="col" class="px-4 py-3">Failed</th>
                <th scope="col" class="px-4 py-3">Open Sessions</th>
                <th scope="col" class="px-4 py-3">Campaigns</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-gray-1">
              <tr
                v-for="row in history"
                :key="row.name"
                class="hover:bg-surface-gray-1 transition-colors"
              >
                <td class="px-4 py-3 font-semibold text-ink-gray-9">
                  {{ formatDay(row.snapshot_date) }}
                </td>
                <td class="px-4 py-3">
                  <Badge
                    :label="row.status"
                    :theme="row.status === 'Ready' ? 'green' : 'amber'"
                    size="sm"
                  />
                </td>
                <td class="px-4 py-3 font-medium text-blue-700">
                  {{ row.messages_in || 0 }}
                </td>
                <td class="px-4 py-3 font-medium text-[#075E54]">
                  {{ row.messages_out || 0 }}
                </td>
                <td class="px-4 py-3">
                  <span
                    :class="row.failed_messages ? 'font-semibold text-red-700' : 'text-ink-gray-5'"
                  >
                    {{ row.failed_messages || 0 }}
                  </span>
                </td>
                <td class="px-4 py-3 font-mono text-ink-gray-7">
                  {{ row.open_conversations || 0 }}
                </td>
                <td class="px-4 py-3 font-mono text-ink-gray-7">
                  {{ row.campaigns_sent || 0 }}
                </td>
              </tr>

              <tr v-if="history.length === 0">
                <td colspan="7" class="py-8 text-center text-xs text-ink-gray-5">
                  No historical snapshots recorded yet.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
