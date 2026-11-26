<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Alert, Badge, Button, ItemListRow, Spinner, toast } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import DeskCard from '@/components/desk/DeskCard.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import { useAccountGate } from '@/composables/useAccountGate'
import { errorText, formatDay, formatTime } from '@/utils/format'
import { getAnalytics, refreshAnalytics } from '@/services/catalogApi'
import { useDesk } from '@/stores/desk'

const desk = useDesk()
const { selectedAccount, accountGateDescription } = useAccountGate()
const live = Boolean(window.csrf_token)

const loading = ref(true)
const error = ref<string | null>(null)
const latest = ref<any | null>(null)
const refreshing = ref<any | null>(null)
const history = ref<any[]>([])
const busy = ref(false)
let timer = 0

const sampleLatest = {
  name: 'snp-today',
  snapshot_date: new Date().toISOString().slice(0, 10),
  whatsapp_account: '',
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

const themeColors: Record<string, string> = {
  blue: '#0369A1',
  teal: '#075E54',
  green: '#047857',
  amber: '#B45309',
  red: '#B91C1C',
  purple: '#6D28D9',
}

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
    },
    {
      label: 'Outgoing Messages',
      value: row.messages_out || 0,
      subtext: 'Free-form & template sends',
      pill: 'Outbound',
      theme: 'teal',
    },
    {
      label: 'Delivery Success Rate',
      value: `${deliveryRate.value}%`,
      subtext: `${row.failed_messages || 0} failed messages`,
      pill: row.failed_messages > 0 ? `${row.failed_messages} issues` : 'Optimal',
      theme: row.failed_messages > 0 ? 'amber' : 'green',
    },
    {
      label: 'Active 24h Sessions',
      value: row.open_conversations || 0,
      subtext: 'Live SLA customer care windows',
      pill: 'Meta Window',
      theme: 'green',
    },
    {
      label: 'Unassigned Queue',
      value: row.unassigned || 0,
      subtext: 'Awaiting team assignment',
      pill: row.unassigned > 0 ? 'Needs Attention' : 'Cleared',
      theme: row.unassigned > 0 ? 'red' : 'green',
    },
    {
      label: 'Campaign Broadcasts',
      value: row.campaigns_sent || 0,
      subtext: 'Outbound marketing campaigns',
      pill: 'Broadcasts',
      theme: 'purple',
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
    const payload = await getAnalytics(selectedAccount.value || undefined)
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
    await refreshAnalytics(selectedAccount.value || undefined)
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
  () => void load(),
)

watch(
  () => desk.account.value,
  () => void load(),
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
  <DeskPage variant="studio">
    <template v-if="!needsAccount" #actions>
      <Button
        variant="subtle"
        size="sm"
        icon-left="lucide-download"
        label="Export CSV"
        @click="exportCsv"
      />
      <Button variant="solid" theme="green" size="sm" icon-left="lucide-refresh-cw" label="Compute Snapshot" loading-text="Computing…" :loading="busy" @click="refresh"/>
    </template>

    <!-- Background Refresh Notification Banner -->
    <div v-if="refreshing" class="shrink-0 border-b border-outline-gray-2 bg-white px-4 py-2">
      <Alert theme="amber" title="Generating a new Metric Snapshot in background… displaying the latest Ready values until computation finishes.">
        <template #prefix>
          <Spinner class="size-4" />
        </template>
      </Alert>
    </div>

    <!-- State Handlers -->
    <DeskEmpty v-if="loading && !latest && !needsAccount" kind="loading" title="Loading WhatsApp metrics…" />
    <DeskEmpty v-else-if="error" kind="error" :message="error" allow-retry @retry="load" />
    <DeskEmpty
      v-else-if="needsAccount"
      kind="account"
      title="No WhatsApp account linked"
      :description="accountGateDescription"
    />
    <DeskEmpty
      v-else-if="!latest"
      title="No Analytics Snapshot Found"
      description="Click 'Compute Snapshot' to calculate and save your first Nudg metric record."
    >
      <Button variant="solid" theme="green" label="Compute First Snapshot" icon-left="lucide-refresh-cw" @click="refresh" class="mt-4"/>
    </DeskEmpty>

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
      </div>

      <!-- Hero KPI Grid (6 Cards) -->
      <section aria-labelledby="kpi-cards-heading">
        <h2 id="kpi-cards-heading" class="sr-only">Executive KPI Cards</h2>
        <div class="grid grid-cols-2 gap-4 lg:grid-cols-3">
          <NumberCard
            v-for="card in cards"
            :key="card.label"
            :title="card.label"
            :value="card.value"
            :color="themeColors[card.theme]"
            :delta-caption="`${card.pill} · ${card.subtext}`"
          />
        </div>
      </section>

      <!-- Traffic Ratio & Delivery Quality Panel (2-Column Grid) -->
      <section class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <!-- Card 1: Inbound vs Outbound Message Ratio -->
        <DeskCard
          title="Traffic Volume Distribution"
          description="Inbound customer queries vs outbound responses & templates"
          class="space-y-4"
        >
          <template #actions>
            <span class="text-xs font-semibold text-ink-gray-8">{{ totalMessages }} total</span>
          </template>

          <!-- Ratio Progress Bar -->
          <div class="space-y-2">
            <div class="flex h-3 w-full overflow-hidden rounded-full bg-surface-gray-2">
              <div
                class="bg-blue-600 transition-all duration-500"
                :style="`width: ${inboundPercentage}%`"
                title="Inbound Messages"
              />
              <div
                class="bg-surface-green-7 transition-all duration-500"
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
                <span class="size-2 rounded-full bg-surface-green-7" />
                <span class="text-ink-gray-7">Outbound: <strong>{{ latest.messages_out }}</strong> ({{ outboundPercentage }}%)</span>
              </div>
            </div>
          </div>

          <Alert
            theme="blue"
            title="Healthy ratio"
            description="Healthy omnichannel desks typically maintain a 1:1.5 to 1:2 ratio of inbound to outbound messages, reflecting prompt replies and automated notifications."
          />
        </DeskCard>

        <!-- Card 2: Meta 24-Hour SLA & Quality Rating -->
        <DeskCard
          title="Meta SLA & Delivery Health"
          description="Message delivery reliability and active service sessions"
          class="space-y-4"
        >
          <template v-if="deliveryRate >= 95" #actions>
            <Badge theme="green" variant="subtle" size="md" label="High Quality" />
          </template>

          <div class="grid grid-cols-2 gap-3">
            <NumberCard
              title="Delivery success"
              :value="`${deliveryRate}%`"
              color="#047857"
              delta-caption="Carrier & Meta handoff rate"
            />
            <NumberCard
              title="SLA window sessions"
              :value="latest.open_conversations"
              color="#047857"
              delta-caption="Active customer care sessions"
            />
          </div>

          <Alert
            theme="gray"
            title="Quality Rating"
            description="Keeping message failures under 2% protects your Meta WABA tier limits and ensures uninterrupted outbound broadcasting."
          />
        </DeskCard>
      </section>

      <!-- Snapshot History Table -->
      <DeskCard
        title="Snapshot Audit History"
        description="Historical daily WhatsApp performance snapshots"
        :padding="false"
        class="[&>div:first-child]:mb-0 [&>div:first-child]:px-4 [&>div:first-child]:py-3"
      >
        <template #actions>
          <span class="text-xs text-ink-gray-5">{{ history.length }} records</span>
        </template>

        <div v-if="history.length === 0" class="border-t border-outline-gray-1 py-8 text-center text-xs text-ink-gray-5">
          No historical snapshots recorded yet.
        </div>
        <div v-else class="divide-y divide-outline-gray-1 border-t border-outline-gray-1">
          <ItemListRow
            v-for="row in history"
            :key="row.name"
            as="div"
            size="lg"
            class="px-4 py-3 hover:bg-surface-gray-1"
          >
            <template #label>
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-sm font-semibold text-ink-gray-9">{{ formatDay(row.snapshot_date) }}</span>
                <Badge
                  :label="row.status"
                  :theme="row.status === 'Ready' ? 'green' : 'amber'"
                  size="sm"
                />
              </div>
            </template>
            <template #suffix>
              <div class="flex flex-wrap items-center justify-end gap-2 text-xs">
                <Badge :label="`In: ${row.messages_in || 0}`" variant="subtle" theme="blue" size="sm" />
                <Badge :label="`Out: ${row.messages_out || 0}`" variant="subtle" theme="green" size="sm" />
                <Badge
                  :label="`Failed: ${row.failed_messages || 0}`"
                  variant="subtle"
                  :theme="row.failed_messages ? 'red' : 'gray'"
                  size="sm"
                />
                <Badge :label="`Open: ${row.open_conversations || 0}`" variant="subtle" theme="gray" size="sm" />
                <Badge :label="`Campaigns: ${row.campaigns_sent || 0}`" variant="subtle" theme="gray" size="sm" />
              </div>
            </template>
          </ItemListRow>
        </div>
      </DeskCard>
    </div>
  </DeskPage>
</template>
