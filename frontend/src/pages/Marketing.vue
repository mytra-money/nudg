<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Badge, Button, Dialog, dialog, FormControl, TextInput, toast } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import DeskCard from '@/components/desk/DeskCard.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import DeskSplit from '@/components/desk/DeskSplit.vue'
import { errorText, formatDay, initials } from '@/utils/format'
import { formatErrorMessage } from '@/utils/errors'
import { createCampaign, deleteCampaign, getCampaign, listCampaigns, listRecipientLists, listRecipientProfiles, runCampaign, updateCampaign } from '@/services/catalogApi'
import { isManager, useDesk } from '@/stores/desk'
import { accountArg } from '@/utils/accountSelection'

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
const statusFilter = ref<'all' | 'Completed' | 'Draft' | 'Scheduled' | 'In Progress'>('all')

const confirmRunOpen = ref(false)
const editorOpen = ref(false)
const editorMode = ref<'create' | 'edit'>('create')
const editingName = ref('')
const saving = ref(false)
const recipientsReady = ref(true)
const recipientLists = ref<any[]>([])
const profiles = ref<any[]>([])
const form = ref({
  name: '',
  description: '',
  whatsapp_account: '',
  recipient_type: 'WA Recipient List',
  recipient: '',
  whatsapp_template: '',
  start_date: '',
  trigger_time: '',
  send_after_days: '0',
})
const recipientTypeOptions = [
  { label: 'Recipient list', value: 'WA Recipient List' },
  { label: 'Profile', value: 'WA Profile' },
]
const statusFilterOptions = computed(() => [
  { label: `All (${rows.value.length})`, value: 'all', active: 'bg-[#075E54] text-white', idle: 'bg-surface-gray-2 text-ink-gray-6 hover:bg-surface-gray-3' },
  { label: 'Scheduled', value: 'Scheduled', active: 'bg-gray-700 text-white', idle: 'bg-gray-100 text-gray-700 hover:bg-gray-200' },
  { label: 'In Progress', value: 'In Progress', active: 'bg-blue-700 text-white', idle: 'bg-blue-50 text-blue-800 hover:bg-blue-100' },
  { label: 'Completed', value: 'Completed', active: 'bg-emerald-700 text-white', idle: 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100' },
  { label: 'Draft', value: 'Draft', active: 'bg-gray-700 text-white', idle: 'bg-gray-100 text-gray-700 hover:bg-gray-200' },
])
const recipientQuery = ref('')

const sampleCampaigns: any[] = [
  {
    name: 'cmp-festive-01',
    campaign_name: 'Festive Allocation Early Access',
    whatsapp_channel: 'Sundarban Sales',
    whatsapp_account: 'Sundarban Sales',
    template: 'festive_allocation',
    recipient_type: 'WA Recipient List',
    recipient: 'Sales opted-in',
    start_date: new Date(Date.now() - 3600000 * 24).toISOString().slice(0, 10),
    end_date: new Date(Date.now() - 3600000 * 24).toISOString().slice(0, 10),
    trigger_time: '09:00',
    send_after_days: 0,
    status: 'Completed',
    can_edit: false,
    sent_count: 240,
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
    recipient_type: 'WA Profile',
    recipient: 'Rafiq Traders',
    start_date: new Date(Date.now() - 3600000 * 48).toISOString().slice(0, 10),
    end_date: new Date(Date.now() - 3600000 * 48).toISOString().slice(0, 10),
    trigger_time: '10:30',
    send_after_days: 0,
    status: 'In Progress',
    can_edit: true,
    sent_count: 120,
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
    recipient_type: 'WA Recipient List',
    recipient: 'Sales opted-in',
    start_date: new Date(Date.now() + 3600000 * 24).toISOString().slice(0, 10),
    end_date: new Date(Date.now() + 3600000 * 24 * 2).toISOString().slice(0, 10),
    trigger_time: '11:00',
    send_after_days: 1,
    status: 'Scheduled',
    can_edit: true,
    sent_count: 0,
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

const currentAccount = computed(() => accountArg(desk.account.value) || '')

function forAccount<T extends { whatsapp_account?: string }>(list: T[]): T[] {
  const account = currentAccount.value
  if (!account) return list
  return list.filter((row) => !row.whatsapp_account || row.whatsapp_account === account)
}

const demoCampaigns = ref<any[]>([...sampleCampaigns])

function loadSample() {
  recipientLists.value = forAccount([
    { name: 'Sales opted-in', list_name: 'Sales opted-in', whatsapp_account: 'Sundarban Sales' },
    { name: 'Dispatch customers', list_name: 'Dispatch customers', whatsapp_account: 'Sundarban Dispatch' },
  ])
  profiles.value = forAccount([
    { name: 'Meera Iyer', profile_name: 'Meera Iyer', phone_number: '+91 98450 22119', whatsapp_account: 'Sundarban Sales' },
    { name: 'Rafiq Traders', profile_name: 'Rafiq Traders', phone_number: '+91 33 4065 1180', whatsapp_account: 'Sundarban Dispatch' },
  ])
  rows.value = forAccount(demoCampaigns.value)
  const current = selected.value && rows.value.find((row) => row.name === selected.value.name)
  selected.value = current || rows.value[0] || null
}

async function load() {
  loading.value = true
  error.value = null
  try {
    if (!live) {
      loadSample()
      return
    }
    const account = currentAccount.value || undefined
    recipientLists.value = (await listRecipientLists(account).catch(() => [])) || []
    profiles.value = (await listRecipientProfiles(account).catch(() => [])) || []
    const result = await listCampaigns(account)
    rows.value = result || []
    const current = selected.value && rows.value.find((row) => row.name === selected.value.name)
    if (current) {
      selected.value = await getCampaign(current.name).catch(() => current)
    } else {
      selected.value = rows.value[0] || null
    }
  } catch (caught) {
    if (!live) {
      loadSample()
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
        match.status = 'In Progress'
        match.sent_count = (match.recipients || []).length
        match.can_edit = false
      }
      toast.success('Bulk message created (Simulation)')
      confirmRunOpen.value = false
      return
    }
    const result = await runCampaign(name)
    toast.success(result?.queued ? 'Bulk message created' : 'Nothing is due at this trigger time yet')
    confirmRunOpen.value = false
    await load()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    busy.value = false
  }
}

const templateOptions = computed(() => {
  const account = form.value.whatsapp_account
  return (desk.inbox.value?.templates || [])
    .filter((row) => !account || !row.whatsapp_account || row.whatsapp_account === account)
    .map((row) => ({
      label: row.template_label || row.template_name || row.name,
      value: row.name,
    }))
})

const recipientListOptions = computed(() => {
  const account = form.value.whatsapp_account
  return recipientLists.value
    .filter((row) => !account || !row.whatsapp_account || row.whatsapp_account === account)
    .map((row) => ({
      label: row.list_name || row.name,
      value: row.name,
    }))
})

const profileOptions = computed(() => {
  const account = form.value.whatsapp_account
  return profiles.value
    .filter((row) => !account || !row.whatsapp_account || row.whatsapp_account === account)
    .map((row) => ({
      label: row.phone_number ? `${row.profile_name || row.name} · ${row.phone_number}` : row.profile_name || row.name,
      value: row.name,
    }))
})

const recipientOptions = computed(() =>
  form.value.recipient_type === 'WA Profile' ? profileOptions.value : recipientListOptions.value,
)

function setRecipientType(value: unknown) {
  const next = String(value || 'WA Recipient List')
  if (next !== form.value.recipient_type) form.value.recipient = ''
  form.value.recipient_type = next
}

function blankForm() {
  return {
    name: '',
    description: '',
    whatsapp_account: currentAccount.value,
    recipient_type: 'WA Recipient List',
    recipient: '',
    whatsapp_template: '',
    start_date: '',
    trigger_time: '',
    send_after_days: '0',
  }
}

function firstSchedule(row: any) {
  const schedules = row?.whatsapp_schedules
  if (Array.isArray(schedules) && schedules.length) return schedules[0]
  return null
}

function canEdit(row: any) {
  if (row?.can_edit === false) return false
  const status = row?.status || 'Draft'
  return status === 'Draft' || status === 'Scheduled' || status === 'In Progress'
}

function dateOnly(value: string | null | undefined) {
  if (!value) return ''
  return String(value).slice(0, 10)
}

function timeOnly(value: string | null | undefined) {
  if (!value) return ''
  return String(value).slice(0, 5)
}

const previewEnd = computed(() => {
  if (!form.value.start_date) return ''
  const start = new Date(`${form.value.start_date}T00:00:00`)
  start.setDate(start.getDate() + Number(form.value.send_after_days || 0))
  const month = String(start.getMonth() + 1).padStart(2, '0')
  const day = String(start.getDate()).padStart(2, '0')
  return `${start.getFullYear()}-${month}-${day}`
})

function fillForm(row: any) {
  const schedule = firstSchedule(row)
  form.value = {
    name: row.campaign_name || row.name || '',
    description: row.description || row.campaign_description || '',
    whatsapp_account: currentAccount.value || row.whatsapp_account || '',
    recipient_type: row.recipient_type || 'WA Recipient List',
    recipient: row.recipient || '',
    whatsapp_template: schedule?.whatsapp_template || row.whatsapp_template || row.template || '',
    start_date: dateOnly(row.start_date),
    trigger_time: timeOnly(row.trigger_time),
    send_after_days: String(schedule?.send_after_days ?? row.send_after_days ?? 0),
  }
}

function schedulePayload() {
  if (!form.value.whatsapp_template) return []
  return [
    {
      whatsapp_template: form.value.whatsapp_template,
      send_after_days: Number(form.value.send_after_days || 0),
    },
  ]
}

function startCreate() {
  editorMode.value = 'create'
  editingName.value = ''
  recipientsReady.value = true
  form.value = blankForm()
  editorOpen.value = true
}

async function startEdit(row: any) {
  editorMode.value = 'edit'
  editingName.value = row.name
  recipientsReady.value = !live
  fillForm(row)
  editorOpen.value = true
  if (!live || !row.name) return
  try {
    const full = await getCampaign(row.name)
    if (editingName.value !== row.name) return
    fillForm(full)
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
        else demoCampaigns.value = demoCampaigns.value.filter((row) => row.name !== campaign.name)
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
  if (!form.value.recipient) {
    toast.error(form.value.recipient_type === 'WA Profile' ? 'Select a profile.' : 'Select a recipient list.')
    return
  }
  if (!form.value.start_date) {
    toast.error('Start date is required.')
    return
  }
  if (!form.value.trigger_time) {
    toast.error('Trigger time is required.')
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
        recipient_type: form.value.recipient_type,
        recipient: form.value.recipient,
        template: form.value.whatsapp_template,
        whatsapp_template: form.value.whatsapp_template,
        send_after_days: Number(form.value.send_after_days || 0),
        status: 'Scheduled',
        can_edit: true,
        start_date: form.value.start_date || null,
        end_date: previewEnd.value || null,
        trigger_time: form.value.trigger_time,
        sent_count: 0,
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
      demoCampaigns.value = [row, ...demoCampaigns.value.filter((item) => item.name !== row.name)]
      if (editorMode.value === 'edit' && selected.value) {
        demoCampaigns.value = demoCampaigns.value.map((item) => (item.name === selected.value.name ? selected.value : item))
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
            recipient_type: form.value.recipient_type,
            recipient: form.value.recipient,
            start_date: form.value.start_date,
            trigger_time: form.value.trigger_time,
            schedules: schedulePayload(),
          })
        : await createCampaign({
            name,
            campaign_description: form.value.description.trim(),
            whatsapp_account: form.value.whatsapp_account || undefined,
            recipient_type: form.value.recipient_type,
            recipient: form.value.recipient,
            start_date: form.value.start_date,
            trigger_time: form.value.trigger_time,
            schedules: schedulePayload(),
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
const totalRecipients = computed(() => rows.value.reduce((acc, c) => acc + (c.recipients?.length || 0), 0))
const totalSent = computed(() => rows.value.reduce((acc, c) => acc + (c.sent_count || 0), 0))
const totalFailed = computed(() => rows.value.reduce((acc, c) => acc + (c.failed_count || 0), 0))

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
    if (!recipientQuery.value.trim()) return true
    const term = recipientQuery.value.toLowerCase()
    return (
      (r.profile || r.recipient_name || '').toLowerCase().includes(term) ||
      (r.phone_number || '').toLowerCase().includes(term)
    )
  })
})

onMounted(() => {
  if (!desk.inbox.value) void desk.load()
  void load()
})

watch(
  () => desk.account.value,
  () => void load(),
)
</script>

<template>
  <DeskPage variant="studio">
    <template #actions>
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
    </template>

    <!-- Top KPI Performance Funnel Bar -->
    <template #kpi>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <NumberCard title="Broadcasts" :value="totalCampaignsCount" color="#374151" delta-caption="whatsapp campaigns" />
        <NumberCard title="Recipients" :value="totalRecipients" color="#075E54" delta-caption="loaded from profile or list" />
        <NumberCard title="Messages Sent" :value="totalSent" color="#047857" delta-caption="from bulk messages" />
        <NumberCard title="Failed Sends" :value="totalFailed" color="#B91C1C" delta-caption="from bulk messages" />
      </div>
    </template>

    <!-- Content State Handlers -->
    <DeskEmpty v-if="loading && !rows.length" kind="loading" title="Loading campaigns…" />
    <DeskEmpty v-else-if="error" kind="error" :message="error" allow-retry @retry="load" />
    <DeskEmpty
      v-else-if="!rows.length"
      kind="empty"
      title="No broadcasts yet"
      description="Create a WhatsApp Campaign with a template, a profile or recipient list, and the dates that send the bulk message."
    >
      <Button
        variant="solid"
        class="mt-4 bg-[#075E54] text-white hover:bg-[#128C7E]"
        v-if="isManager"
        label="Create Your First Campaign"
        icon-left="lucide-plus"
        @click="startCreate()"
      />
    </DeskEmpty>

    <!-- Master-Detail Workspace Grid -->
    <DeskSplit
      v-else
      :narrow="narrow"
      :show-detail="showDetail"
      columns="minmax(0,380px) minmax(0,1fr)"
    >
      <!-- Left Column: Campaign List -->
      <template #master>
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
              <span class="truncate">{{ row.recipient || 'No audience' }}</span>
              <span>Sent: <strong class="text-ink-gray-8">{{ row.sent_count || 0 }}</strong></span>
              <span v-if="row.failed_count" class="text-red-600 font-semibold">
                {{ row.failed_count }} fail
              </span>
            </div>
          </button>

          <div v-if="filteredRows.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
            No campaigns found matching your search.
          </div>
        </div>
      </template>

      <!-- Right Column: Campaign Inspector & Recipient Audit Funnel -->
      <template #detail>
      <div class="flex min-h-0 flex-1 flex-col overflow-y-auto">
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
                Template: <strong class="font-mono text-[#075E54]">{{ selected.template || '—' }}</strong>
                <span v-if="selected.start_date">
                  · {{ formatDay(selected.start_date) }}<span v-if="selected.end_date"> – {{ formatDay(selected.end_date) }}</span>
                </span>
                <span v-if="selected.trigger_time"> · {{ timeOnly(selected.trigger_time) }}</span>
                <span v-if="selected.recipient"> · {{ selected.recipient }}</span>
              </p>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <Button
                v-if="isManager && (selected.status === 'Scheduled' || selected.status === 'In Progress')"
                variant="solid"
                class="bg-[#075E54] text-white hover:bg-[#128C7E]"
                label="Send bulk message"
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
            <div class="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
              <DeskCard as="div" :padding="false" class="p-3.5">
                <span class="text-xs font-medium text-ink-gray-5">Recipients</span>
                <p class="mt-1 text-2xl font-bold text-ink-gray-9">{{ selected.recipients?.length || 0 }}</p>
              </DeskCard>
              <DeskCard as="div" :padding="false" class="p-3.5">
                <span class="text-xs font-medium text-ink-gray-5">Sent</span>
                <p class="mt-1 text-2xl font-bold text-emerald-700">{{ selected.sent_count || 0 }}</p>
              </DeskCard>
              <DeskCard as="div" :padding="false" class="p-3.5">
                <span class="text-xs font-medium text-ink-gray-5">Failed</span>
                <p class="mt-1 text-2xl font-bold" :class="selected.failed_count ? 'text-red-700' : 'text-ink-gray-5'">
                  {{ selected.failed_count || 0 }}
                </p>
              </DeskCard>
            </div>
          </section>

          <!-- Recipient Audit List -->
          <section aria-labelledby="recipients-heading" class="space-y-3">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
              <h3 id="recipients-heading" class="text-xs font-bold uppercase tracking-wider text-ink-gray-5">
                Target Recipients ({{ selected.recipients?.length || 0 }})
              </h3>

              <FormControl
                v-model="recipientQuery"
                type="text"
                class="w-48 text-xs"
                placeholder="Search recipient…"
              />
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
      </div>
      </template>
    </DeskSplit>

    <Dialog v-model="editorOpen" :title="editorMode === 'edit' ? 'Edit campaign' : 'New campaign'">
      <div class="space-y-3 py-1 text-sm">
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
          :model-value="form.recipient_type"
          type="select"
          label="Recipient type"
          :options="recipientTypeOptions"
          @update:model-value="setRecipientType"
        />
        <FormControl
          v-model="form.recipient"
          type="select"
          :label="form.recipient_type === 'WA Profile' ? 'Profile' : 'Recipient list'"
          :options="recipientOptions"
        />
        <FormControl
          v-model="form.whatsapp_template"
          type="select"
          label="WhatsApp template"
          :options="templateOptions"
        />
        <div class="grid grid-cols-3 gap-3">
          <FormControl v-model="form.start_date" type="date" label="Start date" />
          <FormControl :model-value="previewEnd" type="date" label="End date" disabled />
          <FormControl v-model="form.trigger_time" type="time" label="Trigger time" />
        </div>
        <FormControl v-model="form.send_after_days" type="number" label="Send after (days)" />
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
    <Dialog v-model="confirmRunOpen" title="Create bulk message" size="lg">
      <div v-if="selected" class="space-y-4 py-2 text-xs">
        <div class="rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-amber-900 leading-relaxed">
          <p class="font-bold flex items-center gap-1.5">
            <span class="lucide-alert-triangle size-4 text-amber-600" /> Confirm Outbound Send
          </p>
          <p class="mt-1">
            This creates a bulk message for <strong>{{ selected.campaign_name }}</strong> to <strong>{{ selected.recipients?.length || 0 }} recipients</strong> on <strong>{{ selected.whatsapp_account }}</strong>. It sends only while today is between the start and end dates.
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
            label="Create bulk message"
            icon-left="lucide-send"
            :loading="busy"
            @click="run(selected.name)"
          />
        </div>
      </template>
    </Dialog>
  </DeskPage>
</template>
