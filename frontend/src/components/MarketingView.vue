<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Dialog, Select, TextInput, toast } from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { errorText, formatDay, formatTime, initials } from '@/format'
import { formatErrorMessage } from '@/errors'
import { createCampaign, deskForm, getCampaign, listCampaigns, runCampaign, updateCampaign } from '@/phase2'
import { isManager, useDesk } from '@/desk'

const desk = useDesk()
const live = Boolean(window.csrf_token)

const loading = ref(true)
const error = ref<string | null>(null)
const rows = ref<any[]>([])
const selected = ref<any | null>(null)
const busy = ref(false)

const query = ref('')
const statusFilter = ref<'all' | 'Completed' | 'Draft' | 'In Progress' | 'Failed'>('all')

const confirmRunOpen = ref(false)
const editorOpen = ref(false)
const editorMode = ref<'create' | 'edit'>('create')
const editingName = ref('')
const saving = ref(false)
const form = ref({
  name: '',
  description: '',
  whatsapp_account: '',
  whatsapp_template: '',
})
const recipientQuery = ref('')
const recipientStatusFilter = ref<'all' | 'Read' | 'Delivered' | 'Failed' | 'Pending'>('all')

const sampleCampaigns: any[] = [
  {
    name: 'cmp-festive-01',
    campaign_name: 'Festive Allocation Early Access',
    whatsapp_channel: 'Sundarban Sales',
    whatsapp_account: 'Sundarban Sales',
    template: 'festive_allocation',
    status: 'Completed',
    scheduled_at: new Date(Date.now() - 3600000 * 24).toISOString(),
    sent_count: 240,
    delivered_count: 236,
    read_count: 218,
    failed_count: 4,
    modified: new Date(Date.now() - 3600000 * 12).toISOString(),
    recipients: [
      { name: 'rec-1', profile: 'Meera Iyer', phone_number: '+91 98450 22119', status: 'Read', sent_at: new Date(Date.now() - 3600000 * 20).toISOString() },
      { name: 'rec-2', profile: 'Anita Desai', phone_number: '+91 98200 44110', status: 'Delivered', sent_at: new Date(Date.now() - 3600000 * 20).toISOString() },
      { name: 'rec-3', profile: 'Arjun Patel', phone_number: '+91 98250 44218', status: 'Read', sent_at: new Date(Date.now() - 3600000 * 20).toISOString() },
      { name: 'rec-4', profile: 'Hotel Grand Chowringhee', phone_number: '+91 33 2223 8890', status: 'Failed', error_message: 'Contact opted out of marketing broadcasts' },
    ],
  },
  {
    name: 'cmp-dispatch-02',
    campaign_name: 'Weekly Warehouse Dispatch Notice',
    whatsapp_channel: 'Sundarban Dispatch',
    whatsapp_account: 'Sundarban Dispatch',
    template: 'dispatch_notice',
    status: 'Completed',
    scheduled_at: new Date(Date.now() - 3600000 * 48).toISOString(),
    sent_count: 120,
    delivered_count: 118,
    read_count: 112,
    failed_count: 2,
    modified: new Date(Date.now() - 3600000 * 40).toISOString(),
    recipients: [
      { name: 'rec-5', profile: 'Rafiq Traders', phone_number: '+91 33 4065 1180', status: 'Read', sent_at: new Date(Date.now() - 3600000 * 42).toISOString() },
      { name: 'rec-6', profile: 'Arjun Patel', phone_number: '+91 98250 44218', status: 'Delivered', sent_at: new Date(Date.now() - 3600000 * 42).toISOString() },
    ],
  },
  {
    name: 'cmp-catalog-03',
    campaign_name: 'Q4 Fresh Cardamom Lot Booking',
    whatsapp_channel: 'Sundarban Sales',
    whatsapp_account: 'Sundarban Sales',
    template: 'price_list',
    status: 'Draft',
    scheduled_at: null,
    sent_count: 0,
    delivered_count: 0,
    read_count: 0,
    failed_count: 0,
    modified: new Date().toISOString(),
    recipients: [
      { name: 'rec-7', profile: 'Meera Iyer', phone_number: '+91 98450 22119', status: 'Pending' },
      { name: 'rec-8', profile: 'Rafiq Traders', phone_number: '+91 33 4065 1180', status: 'Pending' },
      { name: 'rec-9', profile: 'Anita Desai', phone_number: '+91 98200 44110', status: 'Pending' },
      { name: 'rec-10', profile: 'Arjun Patel', phone_number: '+91 98250 44218', status: 'Pending' },
    ],
  },
]

async function load() {
  loading.value = true
  error.value = null
  try {
    if (!live) {
      rows.value = sampleCampaigns
      if (!selected.value && rows.value.length) {
        selected.value = rows.value[0]
      }
      return
    }
    const result = await listCampaigns()
    rows.value = result || []
    if (selected.value) {
      selected.value = await getCampaign(selected.value.name).catch(() => selected.value)
    } else if (rows.value.length) {
      selected.value = rows.value[0]
    }
  } catch (caught) {
    if (!live) {
      rows.value = sampleCampaigns
      selected.value = rows.value[0]
    } else {
      error.value = errorText(caught)
    }
  } finally {
    loading.value = false
  }
}

async function open(row: any) {
  try {
    if (!live) {
      const found = sampleCampaigns.find((c) => c.name === row.name)
      selected.value = found || row
      return
    }
    selected.value = await getCampaign(row.name)
  } catch (caught) {
    selected.value = row
  }
}

async function run(name: string) {
  busy.value = true
  try {
    if (!live) {
      const match = rows.value.find((c) => c.name === name)
      if (match) {
        match.status = 'Completed'
        match.sent_count = (match.recipients || []).length
        match.delivered_count = match.sent_count
        match.read_count = Math.floor(match.sent_count * 0.8)
        match.recipients?.forEach((r: any) => (r.status = 'Delivered'))
      }
      toast.success('Campaign queued and processed (Simulation)')
      confirmRunOpen.value = false
      return
    }
    const result = await runCampaign(name)
    toast.success(result?.queued ? 'Campaign queued for execution' : 'Campaign is already running')
    confirmRunOpen.value = false
    await load()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    busy.value = false
  }
}

const accountOptions = computed(() =>
  (desk.inbox.value?.accounts || []).map((row) => ({
    label: row.account_name || row.name,
    value: row.name,
  })),
)

const templateOptions = computed(() => {
  const account = form.value.whatsapp_account
  return (desk.inbox.value?.templates || [])
    .filter((row) => !account || !row.whatsapp_account || row.whatsapp_account === account)
    .map((row) => ({
      label: row.template_label || row.template_name || row.name,
      value: row.name,
    }))
})

function canEdit(row: any) {
  const status = row?.status || 'Draft'
  return status === 'Draft' || status === 'Scheduled'
}

function openDesk(name?: string) {
  window.location.href = deskForm('UTM Campaign', name)
}

function startCreate() {
  editorMode.value = 'create'
  editingName.value = ''
  form.value = {
    name: '',
    description: '',
    whatsapp_account: accountOptions.value[0]?.value || '',
    whatsapp_template: '',
  }
  editorOpen.value = true
}

function startEdit(row: any) {
  editorMode.value = 'edit'
  editingName.value = row.name
  form.value = {
    name: row.campaign_name || row.name || '',
    description: row.description || row.campaign_description || '',
    whatsapp_account: row.whatsapp_account || '',
    whatsapp_template: row.whatsapp_template || row.template || '',
  }
  editorOpen.value = true
}

async function saveCampaign() {
  const name = form.value.name.trim()
  if (!name) {
    toast.error('Campaign name is required.')
    return
  }
  saving.value = true
  try {
    if (!live) {
      const row = {
        name: editorMode.value === 'edit' ? editingName.value || name : name,
        campaign_name: name,
        description: form.value.description.trim(),
        campaign_description: form.value.description.trim(),
        whatsapp_channel: form.value.whatsapp_account,
        whatsapp_account: form.value.whatsapp_account,
        template: form.value.whatsapp_template,
        whatsapp_template: form.value.whatsapp_template,
        status: 'Draft',
        scheduled_at: null,
        sent_count: 0,
        delivered_count: 0,
        read_count: 0,
        failed_count: 0,
        modified: new Date().toISOString(),
        recipients: editorMode.value === 'edit' ? selected.value?.recipients || [] : [],
      }
      if (editorMode.value === 'edit') {
        const index = rows.value.findIndex((item) => item.name === editingName.value)
        if (index >= 0) rows.value[index] = { ...rows.value[index], ...row, status: rows.value[index].status }
        selected.value = rows.value[index] || row
      } else {
        rows.value = [row, ...rows.value]
        selected.value = row
      }
      editorOpen.value = false
      toast.success(editorMode.value === 'edit' ? 'Campaign updated' : 'Campaign created')
      return
    }
    const saved =
      editorMode.value === 'edit'
        ? await updateCampaign({
            name: editingName.value,
            campaign_name: name,
            campaign_description: form.value.description.trim(),
            whatsapp_account: form.value.whatsapp_account || undefined,
            whatsapp_template: form.value.whatsapp_template || undefined,
          })
        : await createCampaign({
            name,
            campaign_description: form.value.description.trim(),
            whatsapp_account: form.value.whatsapp_account || undefined,
            whatsapp_template: form.value.whatsapp_template || undefined,
          })
    editorOpen.value = false
    toast.success(editorMode.value === 'edit' ? 'Campaign updated' : 'Campaign created')
    await load()
    if (saved?.name) selected.value = await getCampaign(saved.name).catch(() => saved)
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    saving.value = false
  }
}

// Top KPI metrics
const totalCampaignsCount = computed(() => rows.value.length)
const totalSent = computed(() => rows.value.reduce((acc, c) => acc + (c.sent_count || 0), 0))
const totalDelivered = computed(() => rows.value.reduce((acc, c) => acc + (c.delivered_count || 0), 0))
const totalRead = computed(() => rows.value.reduce((acc, c) => acc + (c.read_count || 0), 0))

const overallDeliveryRate = computed(() => {
  if (totalSent.value === 0) return 100
  return Math.round((totalDelivered.value / totalSent.value) * 100)
})

const overallReadRate = computed(() => {
  if (totalDelivered.value === 0) return 0
  return Math.round((totalRead.value / totalDelivered.value) * 100)
})

// Filtered campaigns
const filteredRows = computed(() => {
  return rows.value.filter((row) => {
    if (statusFilter.value !== 'all' && row.status !== statusFilter.value) return false
    if (!query.value.trim()) return true
    const term = query.value.toLowerCase()
    return (
      (row.campaign_name || '').toLowerCase().includes(term) ||
      (row.template || '').toLowerCase().includes(term) ||
      (row.whatsapp_account || '').toLowerCase().includes(term)
    )
  })
})

// Recipient filter in selected campaign
const filteredRecipients = computed(() => {
  if (!selected.value || !selected.value.recipients) return []
  return selected.value.recipients.filter((r: any) => {
    if (recipientStatusFilter.value !== 'all' && r.status !== recipientStatusFilter.value) return false
    if (!recipientQuery.value.trim()) return true
    const term = recipientQuery.value.toLowerCase()
    return (
      (r.profile || '').toLowerCase().includes(term) ||
      (r.phone_number || '').toLowerCase().includes(term)
    )
  })
})

function campaignDeliveryRate(c: any) {
  if (!c.sent_count) return 0
  return Math.round(((c.delivered_count || 0) / c.sent_count) * 100)
}

function campaignReadRate(c: any) {
  if (!c.delivered_count) return 0
  return Math.round(((c.read_count || 0) / c.delivered_count) * 100)
}

onMounted(() => {
  if (!desk.inbox.value) void desk.load()
  void load()
})
</script>

<template>
  <div class="flex h-full min-w-0 flex-col overflow-hidden bg-surface-gray-1">
    <!-- Top Action Header -->
    <header class="flex flex-col gap-3 border-b border-outline-gray-2 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between shrink-0">
      <div>
        <div class="flex items-center gap-2">
          <span class="rounded bg-[#075E54]/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-[#075E54]">
            Outbound Marketing
          </span>
          <span class="text-xs text-ink-gray-5">·</span>
          <span class="text-xs font-medium text-ink-gray-6">WhatsApp Broadcast Campaigns</span>
        </div>
        <h1 class="mt-1 text-xl font-bold tracking-tight text-ink-gray-9">
          Campaign Studio & Funnels
        </h1>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <Button
          variant="subtle"
          size="sm"
          icon="lucide-refresh-cw"
          label="Refresh"
          :loading="loading"
          @click="load"
        />
        <Button
          v-if="isManager"
          variant="solid"
          size="sm"
          class="bg-[#075E54] text-white hover:bg-[#128C7E]"
          icon-left="lucide-plus"
          label="New Campaign"
          @click="openDesk()"
        />
      </div>
    </header>

    <!-- Top KPI Performance Funnel Bar -->
    <section class="border-b border-outline-gray-2 bg-white px-4 py-3 shrink-0">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <!-- Metric 1: Total Broadcasts -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Broadcasts</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-ink-gray-9">{{ totalCampaignsCount }}</span>
            <span class="text-[11px] text-ink-gray-5">campaigns</span>
          </div>
        </div>

        <!-- Metric 2: Messages Sent -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Messages Sent</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-[#075E54]">{{ totalSent }}</span>
            <span class="text-[11px] text-ink-gray-5">total volume</span>
          </div>
        </div>

        <!-- Metric 3: Delivery Rate -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Delivery Rate</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-emerald-700">{{ overallDeliveryRate }}%</span>
            <span class="text-[11px] text-emerald-600 font-medium">({{ totalDelivered }})</span>
          </div>
        </div>

        <!-- Metric 4: Read Rate -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Read / Open Rate</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-blue-700">{{ overallReadRate }}%</span>
            <span class="text-[11px] text-blue-600 font-medium">({{ totalRead }})</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Content State Handlers -->
    <LoadingState v-if="loading && !rows.length" label="Loading campaigns…" />
    <ErrorState v-else-if="error" :message="error" allow-retry @retry="load" />
    <EmptyState
      v-else-if="!rows.length"
      title="No broadcasts yet"
      description="Create a UTM Campaign with a WhatsApp template to broadcast offers, announcements, or notifications."
    >
      <Button
        variant="solid"
        class="mt-4 bg-[#075E54] text-white hover:bg-[#128C7E]"
        v-if="isManager"
        label="Create Your First Campaign"
        icon-left="lucide-plus"
        @click="openDesk()"
      />
    </EmptyState>

    <!-- Master-Detail Workspace Grid -->
    <div v-else class="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,380px)_1fr] overflow-hidden">
      <!-- Left Column: Campaign List -->
      <aside class="flex flex-col border-r border-outline-gray-2 bg-white min-h-0 overflow-hidden">
        <!-- Search & Filter Tabs -->
        <div class="border-b border-outline-gray-2 p-3 space-y-2.5 shrink-0">
          <div class="relative">
            <TextInput
              v-model="query"
              placeholder="Search campaigns or templates…"
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

          <div class="flex items-center gap-1 overflow-x-auto text-xs pb-0.5">
            <button
              type="button"
              class="rounded-full px-2.5 py-0.5 font-medium transition-colors"
              :class="statusFilter === 'all' ? 'bg-[#075E54] text-white' : 'bg-surface-gray-2 text-ink-gray-6 hover:bg-surface-gray-3'"
              @click="statusFilter = 'all'"
            >
              All ({{ rows.length }})
            </button>
            <button
              type="button"
              class="rounded-full px-2.5 py-0.5 font-medium transition-colors"
              :class="statusFilter === 'Completed' ? 'bg-emerald-700 text-white' : 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100'"
              @click="statusFilter = 'Completed'"
            >
              Completed
            </button>
            <button
              type="button"
              class="rounded-full px-2.5 py-0.5 font-medium transition-colors"
              :class="statusFilter === 'Draft' ? 'bg-gray-700 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'"
              @click="statusFilter = 'Draft'"
            >
              Draft
            </button>
            <button
              type="button"
              class="rounded-full px-2.5 py-0.5 font-medium transition-colors"
              :class="statusFilter === 'Failed' ? 'bg-red-700 text-white' : 'bg-red-50 text-red-700 hover:bg-red-100'"
              @click="statusFilter = 'Failed'"
            >
              Failed
            </button>
          </div>
        </div>

        <!-- Campaign Scroller -->
        <div class="min-h-0 flex-1 overflow-y-auto divide-y divide-outline-gray-1">
          <button
            v-for="row in filteredRows"
            :key="row.name"
            type="button"
            class="flex w-full flex-col gap-2 p-3.5 text-left transition-all hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#128C7E]"
            :class="
              selected?.name === row.name
                ? 'border-l-4 border-l-[#075E54] bg-teal-50/70 shadow-2xs'
                : 'border-l-4 border-l-transparent'
            "
            @click="open(row)"
          >
            <div class="flex items-start justify-between gap-2">
              <span class="truncate font-semibold text-sm text-ink-gray-9">
                {{ row.campaign_name }}
              </span>
              <Badge
                :label="row.status"
                :theme="row.status === 'Completed' ? 'green' : row.status === 'Failed' ? 'red' : row.status === 'In Progress' ? 'blue' : 'gray'"
                size="sm"
              />
            </div>

            <div class="flex items-center gap-2 text-xs text-ink-gray-5">
              <span class="inline-flex items-center gap-1 font-medium text-ink-gray-7">
                <span class="lucide-layout-template size-3 text-[#075E54]" />
                {{ row.template }}
              </span>
              <span>·</span>
              <span class="truncate">{{ row.whatsapp_account }}</span>
            </div>

            <!-- Mini Funnel Row -->
            <div class="mt-1 flex items-center justify-between text-[11px] text-ink-gray-5 bg-surface-gray-1/80 rounded px-2 py-1">
              <span>Sent: <strong class="text-ink-gray-8">{{ row.sent_count || 0 }}</strong></span>
              <span>Delivered: <strong class="text-emerald-700">{{ row.delivered_count || 0 }}</strong></span>
              <span>Read: <strong class="text-blue-700">{{ row.read_count || 0 }}</strong></span>
              <span v-if="row.failed_count" class="text-red-600 font-semibold">
                {{ row.failed_count }} fail
              </span>
            </div>
          </button>

          <div v-if="filteredRows.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
            No campaigns found matching your search.
          </div>
        </div>
      </aside>

      <!-- Right Column: Campaign Inspector & Recipient Audit Funnel -->
      <main class="flex flex-col bg-white min-h-0 overflow-y-auto">
        <!-- Active Campaign Inspector -->
        <div v-if="selected" class="p-5 sm:p-6 space-y-6">
          <!-- Inspector Header -->
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-outline-gray-2 pb-5">
            <div>
              <div class="flex items-center gap-2">
                <Badge
                  :label="selected.status"
                  :theme="selected.status === 'Completed' ? 'green' : selected.status === 'Failed' ? 'red' : selected.status === 'In Progress' ? 'blue' : 'gray'"
                />
                <span class="text-xs font-mono text-ink-gray-5">{{ selected.whatsapp_account }}</span>
              </div>
              <h2 class="mt-1.5 text-xl font-bold text-ink-gray-9">
                {{ selected.campaign_name }}
              </h2>
              <p class="text-xs text-ink-gray-5 mt-0.5">
                Template: <strong class="font-mono text-[#075E54]">{{ selected.template }}</strong>
                <span v-if="selected.scheduled_at"> · Scheduled: {{ formatDay(selected.scheduled_at) }}</span>
              </p>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <Button
                v-if="isManager && (selected.status === 'Draft' || selected.status === 'Scheduled')"
                variant="solid"
                class="bg-[#075E54] text-white hover:bg-[#128C7E]"
                label="Run Broadcast"
                icon-left="lucide-send"
                :loading="busy"
                @click="confirmRunOpen = true"
              />
              <Button
                v-if="isManager"
                variant="subtle"
                label="Edit in Desk"
                icon-left="lucide-pencil"
                @click="openDesk(selected.name)"
              />
            </div>
          </div>

          <!-- Error Banner if failed -->
          <div
            v-if="selected.last_error"
            class="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-800"
          >
            <p class="font-semibold flex items-center gap-1.5 text-red-900">
              <span class="lucide-alert-circle size-4" /> Execution Issue Encountered
            </p>
            <p class="mt-1">{{ formatErrorMessage(selected.last_error) }}</p>
          </div>

          <!-- Broadcast Funnel Metrics -->
          <section aria-labelledby="funnel-heading">
            <h3 id="funnel-heading" class="text-xs font-bold uppercase tracking-wider text-ink-gray-5">
              Broadcast Delivery Funnel
            </h3>
            <div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <!-- Sent -->
              <div class="rounded-xl border border-outline-gray-2 bg-surface-gray-1/60 p-3.5">
                <span class="text-xs font-medium text-ink-gray-5">Total Sent</span>
                <p class="mt-1 text-2xl font-bold text-ink-gray-9">{{ selected.sent_count || 0 }}</p>
                <div class="mt-2 h-1.5 w-full rounded-full bg-gray-200">
                  <div class="h-1.5 rounded-full bg-[#075E54]" style="width: 100%" />
                </div>
              </div>

              <!-- Delivered -->
              <div class="rounded-xl border border-outline-gray-2 bg-surface-gray-1/60 p-3.5">
                <div class="flex justify-between items-baseline">
                  <span class="text-xs font-medium text-ink-gray-5">Delivered</span>
                  <span class="text-xs font-semibold text-emerald-700">{{ campaignDeliveryRate(selected) }}%</span>
                </div>
                <p class="mt-1 text-2xl font-bold text-emerald-700">{{ selected.delivered_count || 0 }}</p>
                <div class="mt-2 h-1.5 w-full rounded-full bg-gray-200">
                  <div
                    class="h-1.5 rounded-full bg-emerald-600"
                    :style="`width: ${campaignDeliveryRate(selected)}%`"
                  />
                </div>
              </div>

              <!-- Read -->
              <div class="rounded-xl border border-outline-gray-2 bg-surface-gray-1/60 p-3.5">
                <div class="flex justify-between items-baseline">
                  <span class="text-xs font-medium text-ink-gray-5">Read / Opened</span>
                  <span class="text-xs font-semibold text-blue-700">{{ campaignReadRate(selected) }}%</span>
                </div>
                <p class="mt-1 text-2xl font-bold text-blue-700">{{ selected.read_count || 0 }}</p>
                <div class="mt-2 h-1.5 w-full rounded-full bg-gray-200">
                  <div
                    class="h-1.5 rounded-full bg-blue-600"
                    :style="`width: ${campaignReadRate(selected)}%`"
                  />
                </div>
              </div>

              <!-- Failed -->
              <div class="rounded-xl border border-outline-gray-2 bg-surface-gray-1/60 p-3.5">
                <span class="text-xs font-medium text-ink-gray-5">Failed Sends</span>
                <p class="mt-1 text-2xl font-bold" :class="selected.failed_count ? 'text-red-700' : 'text-ink-gray-5'">
                  {{ selected.failed_count || 0 }}
                </p>
                <div class="mt-2 h-1.5 w-full rounded-full bg-gray-200">
                  <div
                    class="h-1.5 rounded-full bg-red-600"
                    :style="`width: ${selected.sent_count ? Math.round(((selected.failed_count || 0) / selected.sent_count) * 100) : 0}%`"
                  />
                </div>
              </div>
            </div>
          </section>

          <!-- Recipient Audit List -->
          <section aria-labelledby="recipients-heading" class="space-y-3">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
              <h3 id="recipients-heading" class="text-xs font-bold uppercase tracking-wider text-ink-gray-5">
                Target Recipients ({{ selected.recipients?.length || 0 }})
              </h3>

              <div class="flex items-center gap-2">
                <div class="relative w-48">
                  <TextInput
                    v-model="recipientQuery"
                    placeholder="Search recipient…"
                    class="w-full text-xs"
                  />
                </div>
                <Select
                  class="w-32 text-xs"
                  :model-value="recipientStatusFilter"
                  :options="[
                    { label: 'All Statuses', value: 'all' },
                    { label: 'Read', value: 'Read' },
                    { label: 'Delivered', value: 'Delivered' },
                    { label: 'Failed', value: 'Failed' },
                    { label: 'Pending', value: 'Pending' },
                  ]"
                  @update:model-value="(val) => (recipientStatusFilter = val as typeof recipientStatusFilter)"
                />
              </div>
            </div>

            <!-- Recipient Items Table -->
            <div class="rounded-xl border border-outline-gray-2 overflow-hidden bg-white">
              <ul class="divide-y divide-outline-gray-1 text-xs">
                <li
                  v-for="rec in filteredRecipients"
                  :key="rec.name || rec.idx || rec.phone_number"
                  class="flex items-center justify-between p-3 hover:bg-surface-gray-1 transition-colors"
                >
                  <div class="flex items-center gap-3 min-w-0">
                    <span class="grid size-8 shrink-0 place-items-center rounded-full bg-teal-100 text-[11px] font-bold text-[#075E54]">
                      {{ initials(rec.profile || rec.phone_number) }}
                    </span>
                    <div class="min-w-0">
                      <p class="font-semibold text-ink-gray-9 truncate">
                        {{ rec.profile || rec.phone_number }}
                      </p>
                      <p class="text-[11px] font-mono text-ink-gray-5">
                        {{ rec.phone_number || rec.profile }}
                      </p>
                      <p v-if="rec.error_message" class="text-[11px] text-red-600 mt-0.5">
                        {{ formatErrorMessage(rec.error_message) }}
                      </p>
                    </div>
                  </div>

                  <div class="flex items-center gap-3 shrink-0">
                    <span v-if="rec.sent_at" class="text-[11px] text-ink-gray-5">
                      {{ formatTime(rec.sent_at) }}
                    </span>
                    <Badge
                      :label="rec.status"
                      :theme="rec.status === 'Read' ? 'blue' : rec.status === 'Delivered' ? 'green' : rec.status === 'Failed' ? 'red' : 'gray'"
                      size="sm"
                    />
                  </div>
                </li>

                <li v-if="filteredRecipients.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
                  No recipients found matching your filter.
                </li>
              </ul>
            </div>
          </section>
        </div>

        <!-- Empty Canvas when no campaign is selected -->
        <div v-else class="grid flex-1 place-items-center p-8 text-center text-xs text-ink-gray-5">
          <div class="max-w-sm space-y-3">
            <div class="mx-auto grid size-12 place-items-center rounded-xl bg-teal-50 text-[#075E54]">
              <span class="lucide-megaphone size-6" />
            </div>
            <p class="text-sm font-semibold text-ink-gray-9">Select a Campaign</p>
            <p class="text-ink-gray-5 leading-relaxed">
              Click any campaign from the list on the left to inspect its delivery funnel, target audience, and message delivery status.
            </p>
          </div>
        </div>
      </main>
    </div>

    <Dialog v-model="editorOpen" :title="editorMode === 'edit' ? 'Edit campaign' : 'New campaign'">
      <div class="space-y-3 py-1 text-sm">
        <p class="text-xs text-ink-gray-6">
          The campaign is saved here in NUDG. Name, description, WhatsApp account, and template stay on this page.
        </p>
        <label class="block text-xs font-medium text-ink-gray-7">
          Name
          <TextInput v-model="form.name" class="mt-1" placeholder="Festive allocation" />
        </label>
        <label class="block text-xs font-medium text-ink-gray-7">
          Description
          <textarea
            v-model="form.description"
            rows="3"
            class="mt-1 w-full rounded border border-outline-gray-2 px-2 py-1.5 text-sm text-ink-gray-9"
            placeholder="Optional note for this broadcast"
          />
        </label>
        <label class="block text-xs font-medium text-ink-gray-7">
          WhatsApp account
          <Select
            class="mt-1"
            :model-value="form.whatsapp_account"
            :options="accountOptions"
            @update:model-value="(val) => (form.whatsapp_account = String(val || ''))"
          />
        </label>
        <label class="block text-xs font-medium text-ink-gray-7">
          WhatsApp template
          <Select
            class="mt-1"
            :model-value="form.whatsapp_template"
            :options="templateOptions"
            @update:model-value="(val) => (form.whatsapp_template = String(val || ''))"
          />
        </label>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="editorOpen = false" />
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            :label="editorMode === 'edit' ? 'Save' : 'Create campaign'"
            :loading="saving"
            @click="saveCampaign"
          />
        </div>
      </template>
    </Dialog>

    <!-- Confirm Run Campaign Dialog -->
    <Dialog v-model="confirmRunOpen" title="Launch WhatsApp Broadcast" size="lg">
      <div v-if="selected" class="space-y-4 py-2 text-xs">
        <div class="rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-amber-900 leading-relaxed">
          <p class="font-bold flex items-center gap-1.5">
            <span class="lucide-alert-triangle size-4 text-amber-600" /> Confirm Outbound Send
          </p>
          <p class="mt-1">
            You are about to launch campaign <strong>{{ selected.campaign_name }}</strong> to <strong>{{ selected.recipients?.length || 0 }} recipients</strong> via channel <strong>{{ selected.whatsapp_account }}</strong>.
          </p>
        </div>

        <dl class="divide-y divide-outline-gray-1 border-t border-b border-outline-gray-1 text-xs">
          <div class="flex justify-between py-2">
            <dt class="text-ink-gray-5">WhatsApp Template:</dt>
            <dd class="font-mono font-medium text-ink-gray-9">{{ selected.template }}</dd>
          </div>
          <div class="flex justify-between py-2">
            <dt class="text-ink-gray-5">Channel Sender Line:</dt>
            <dd class="font-medium text-ink-gray-9">{{ selected.whatsapp_account }}</dd>
          </div>
          <div class="flex justify-between py-2">
            <dt class="text-ink-gray-5">Recipients Count:</dt>
            <dd class="font-bold text-[#075E54]">{{ selected.recipients?.length || 0 }} contacts</dd>
          </div>
        </dl>

        <p class="text-[11px] text-ink-gray-5 leading-relaxed">
          Meta WhatsApp Cloud API will charge per delivered marketing template. All recipients must be opted-in.
        </p>
      </div>

      <template #actions>
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="confirmRunOpen = false" />
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Confirm & Launch Broadcast"
            icon-left="lucide-send"
            :loading="busy"
            @click="run(selected.name)"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>
