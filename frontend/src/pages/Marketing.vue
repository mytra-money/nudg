<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Badge, Button, Dialog, dialog, FormControl, Select, TextInput, toast } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import DeskCard from '@/components/desk/DeskCard.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { errorText, formatDay, formatTime, initials } from '@/utils/format'
import { formatErrorMessage } from '@/utils/errors'
import { createCampaign, deleteCampaign, getCampaign, listCampaigns, runCampaign, updateCampaign } from '@/services/catalogApi'
import { isManager, useDesk } from '@/stores/desk'

const desk = useDesk()
const live = Boolean(window.csrf_token)

const loading = ref(true)
const error = ref<string | null>(null)
const rows = ref<any[]>([])
const selected = ref<any | null>(null)
const narrow = useMediaQuery('(max-width: 767px)')
const showDetail = ref(false)
const busy = ref(false)

const query = ref('')
const statusFilter = ref<'all' | 'Completed' | 'Draft' | 'In Progress' | 'Failed'>('all')

const confirmRunOpen = ref(false)
const editorOpen = ref(false)
const editorMode = ref<'create' | 'edit'>('create')
const editingName = ref('')
const saving = ref(false)
const recipientsReady = ref(true)
const form = ref({
  name: '',
  description: '',
  whatsapp_account: '',
  whatsapp_template: '',
  scheduled_at: '',
  recipients: '',
})
const recipientStatusOptions = [
  { label: 'All Statuses', value: 'all' },
  { label: 'Read', value: 'Read' },
  { label: 'Delivered', value: 'Delivered' },
  { label: 'Failed', value: 'Failed' },
  { label: 'Pending', value: 'Pending' },
]
const statusFilterOptions = computed(() => [
  { label: `All (${rows.value.length})`, value: 'all', active: 'bg-[#075E54] text-white', idle: 'bg-surface-gray-2 text-ink-gray-6 hover:bg-surface-gray-3' },
  { label: 'Completed', value: 'Completed', active: 'bg-emerald-700 text-white', idle: 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100' },
  { label: 'Draft', value: 'Draft', active: 'bg-gray-700 text-white', idle: 'bg-gray-100 text-gray-700 hover:bg-gray-200' },
  { label: 'Failed', value: 'Failed', active: 'bg-red-700 text-white', idle: 'bg-red-50 text-red-700 hover:bg-red-100' },
])
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
  showDetail.value = true
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

function recipientLines(recipients: any) {
  if (!recipients) return ''
  if (typeof recipients === 'string') return recipients
  if (!Array.isArray(recipients)) return ''
  return recipients
    .map((row) => (typeof row === 'string' ? row : row?.phone_number || ''))
    .filter(Boolean)
    .join('\n')
}

function toDatetimeLocal(value: string | null | undefined) {
  if (!value) return ''
  return String(value).replace(' ', 'T').slice(0, 16)
}

function fromDatetimeLocal(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return ''
  if (trimmed.length === 16) return `${trimmed.replace('T', ' ')}:00`
  return trimmed.replace('T', ' ')
}

function startCreate() {
  editorMode.value = 'create'
  editingName.value = ''
  recipientsReady.value = true
  form.value = {
    name: '',
    description: '',
    whatsapp_account: accountOptions.value[0]?.value || '',
    whatsapp_template: '',
    scheduled_at: '',
    recipients: '',
  }
  editorOpen.value = true
}

async function startEdit(row: any) {
  editorMode.value = 'edit'
  editingName.value = row.name
  recipientsReady.value = !live
  form.value = {
    name: row.campaign_name || row.name || '',
    description: row.description || row.campaign_description || '',
    whatsapp_account: row.whatsapp_account || '',
    whatsapp_template: row.whatsapp_template || row.template || '',
    scheduled_at: toDatetimeLocal(row.scheduled_at),
    recipients: recipientLines(row.recipients),
  }
  editorOpen.value = true
  if (!live || !row.name) return
  try {
    const full = await getCampaign(row.name)
    if (editingName.value !== row.name) return
    form.value.description = full.campaign_description || full.description || form.value.description
    form.value.scheduled_at = toDatetimeLocal(full.scheduled_at)
    form.value.recipients = recipientLines(full.recipients)
    recipientsReady.value = true
  } catch {
    recipientsReady.value = false
  }
}

function removeCampaign() {
  if (!selected.value || !canEdit(selected.value)) return
  const campaign = selected.value
  dialog.danger({
    title: 'Delete campaign?',
    message: `Remove “${campaign.campaign_name || campaign.name}”?`,
    onConfirm: async () => {
      busy.value = true
      try {
        if (live) await deleteCampaign(campaign.name)
        rows.value = rows.value.filter((row) => row.name !== campaign.name)
        selected.value = null
        toast.success('Campaign deleted')
      } finally {
        busy.value = false
      }
    },
  })
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
        status: form.value.scheduled_at ? 'Scheduled' : 'Draft',
        scheduled_at: fromDatetimeLocal(form.value.scheduled_at) || null,
        recipients: form.value.recipients,
        sent_count: 0,
        delivered_count: 0,
        read_count: 0,
        failed_count: 0,
        modified: new Date().toISOString(),
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
            scheduled_at: fromDatetimeLocal(form.value.scheduled_at),
            recipients: recipientsReady.value ? form.value.recipients : undefined,
          })
        : await createCampaign({
            name,
            campaign_description: form.value.description.trim(),
            whatsapp_account: form.value.whatsapp_account || undefined,
            whatsapp_template: form.value.whatsapp_template || undefined,
            scheduled_at: fromDatetimeLocal(form.value.scheduled_at),
            recipients: form.value.recipients,
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
          @click="startCreate()"
        />
      </div>
    </header>

    <!-- Top KPI Performance Funnel Bar -->
    <section class="border-b border-outline-gray-2 bg-white px-4 py-3 shrink-0">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <NumberCard title="Broadcasts" :value="totalCampaignsCount" color="#374151" delta-caption="campaigns" />
        <NumberCard title="Messages Sent" :value="totalSent" color="#075E54" delta-caption="total volume" />
        <NumberCard
          title="Delivery Rate"
          :value="`${overallDeliveryRate}%`"
          color="#047857"
          :delta-caption="`${totalDelivered} delivered`"
        />
        <NumberCard
          title="Read / Open Rate"
          :value="`${overallReadRate}%`"
          color="#1D4ED8"
          :delta-caption="`${totalRead} read`"
        />
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
        @click="startCreate()"
      />
    </EmptyState>

    <!-- Master-Detail Workspace Grid -->
    <div v-else class="nudg-split nudg-master grid min-h-0 flex-1 grid-cols-1 overflow-hidden md:grid-cols-[minmax(0,380px)_1fr]">
      <!-- Left Column: Campaign List -->
      <aside
        class="min-h-0 flex-col overflow-hidden border-r border-outline-gray-2 bg-white"
        :class="narrow && showDetail ? 'hidden' : 'flex'"
      >
        <!-- Search & Filter Tabs -->
        <div class="border-b border-outline-gray-2 p-3 space-y-2.5 shrink-0">
          <TextInput
            v-model="query"
            type="text"
            placeholder="Search campaigns or templates…"
            class="w-full text-xs"
          >
            <template v-if="query" #suffix>
              <Button variant="ghost" size="sm" icon="lucide-x" aria-label="Clear search" @click="query = ''" />
            </template>
          </TextInput>

          <div class="flex flex-wrap items-center gap-1 pb-0.5">
            <Button
              v-for="option in statusFilterOptions"
              :key="option.value"
              size="sm"
              :variant="statusFilter === option.value ? 'solid' : 'subtle'"
              :class="statusFilter === option.value ? option.active : option.idle"
              :label="option.label"
              @click="statusFilter = option.value as typeof statusFilter"
            />
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
      <main
        class="min-h-0 flex-col overflow-y-auto bg-white"
        :class="narrow && !showDetail ? 'hidden' : 'flex'"
      >
        <div v-if="narrow && selected" class="px-4 pt-3">
          <Button variant="ghost" icon-left="lucide-arrow-left" label="All campaigns" @click="showDetail = false" />
        </div>
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
                v-if="isManager && canEdit(selected)"
                variant="subtle"
                label="Edit"
                icon-left="lucide-pencil"
                @click="startEdit(selected)"
              />
              <Button
                v-if="isManager && canEdit(selected)"
                variant="subtle"
                theme="red"
                label="Delete"
                @click="removeCampaign"
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
              <DeskCard as="div" :padding="false" class="p-3.5">
                <span class="text-xs font-medium text-ink-gray-5">Total Sent</span>
                <p class="mt-1 text-2xl font-bold text-ink-gray-9">{{ selected.sent_count || 0 }}</p>
                <div class="mt-2 h-1.5 w-full rounded-full bg-gray-200">
                  <div class="h-1.5 rounded-full bg-[#075E54]" style="width: 100%" />
                </div>
              </DeskCard>

              <!-- Delivered -->
              <DeskCard as="div" :padding="false" class="p-3.5">
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
              </DeskCard>

              <!-- Read -->
              <DeskCard as="div" :padding="false" class="p-3.5">
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
              </DeskCard>

              <!-- Failed -->
              <DeskCard as="div" :padding="false" class="p-3.5">
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
              </DeskCard>
            </div>
          </section>

          <!-- Recipient Audit List -->
          <section aria-labelledby="recipients-heading" class="space-y-3">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
              <h3 id="recipients-heading" class="text-xs font-bold uppercase tracking-wider text-ink-gray-5">
                Target Recipients ({{ selected.recipients?.length || 0 }})
              </h3>

              <div class="flex items-center gap-2">
                <FormControl
                  v-model="recipientQuery"
                  type="text"
                  class="w-48 text-xs"
                  placeholder="Search recipient…"
                />
                <Select
                  class="w-32 text-xs"
                  :model-value="recipientStatusFilter"
                  :options="recipientStatusOptions"
                  @update:model-value="(val) => (recipientStatusFilter = (String(val || 'all') as typeof recipientStatusFilter))"
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
          Save the broadcast here. A schedule keeps it as Scheduled until it runs. One phone number per line becomes the audience.
        </p>
        <FormControl
          v-model="form.name"
          type="text"
          label="Name"
          placeholder="Festive allocation"
          required
        />
        <FormControl
          v-model="form.description"
          type="textarea"
          label="Description"
          :rows="3"
          placeholder="Optional note for this broadcast"
        />
        <FormControl
          v-model="form.whatsapp_account"
          type="select"
          label="WhatsApp account"
          :options="accountOptions"
        />
        <FormControl
          v-model="form.whatsapp_template"
          type="select"
          label="WhatsApp template"
          :options="templateOptions"
        />
        <FormControl v-model="form.scheduled_at" type="datetime-local" label="Schedule" />
        <FormControl
          v-model="form.recipients"
          type="textarea"
          label="Recipients"
          :rows="4"
          class="[&_textarea]:font-mono"
          placeholder="9198XXXXXXXX&#10;One number per line"
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="editorOpen = false" />
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            :label="editorMode === 'edit' ? 'Save' : 'Create campaign'"
            :loading="saving || (editorMode === 'edit' && !recipientsReady)"
            :disabled="editorMode === 'edit' && !recipientsReady"
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
