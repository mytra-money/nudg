<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Alert, Badge, Button, Checkbox, Dialog, dialog, FormControl, TabButtons, TextInput, toast } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import DeskCard from '@/components/desk/DeskCard.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import DeskSplit from '@/components/desk/DeskSplit.vue'
import { errorText, formatDay, initials } from '@/utils/format'
import { displayTitle } from '@/utils/titles'
import { formatErrorMessage } from '@/utils/errors'
import { createUtmCampaign, createWhatsappSchedule, deleteCampaign, deleteUtmCampaign, getCampaign, getUtmCampaign, listBulkResults, listCampaigns, listRecipientLists, listRecipientProfiles, listUtmCampaigns, runCampaign, updateUtmCampaign, updateWhatsappSchedule } from '@/services/catalogApi'
import { isManager, useDesk } from '@/stores/desk'
import { accountArg } from '@/utils/accountSelection'

const desk = useDesk()
const live = Boolean(window.csrf_token)

const loading = ref(true)
const error = ref<string | null>(null)
const tab = ref<'campaigns' | 'schedules' | 'results'>('campaigns')

function setTab(value: unknown) {
  if (value === 'campaigns' || value === 'schedules' || value === 'results') tab.value = value
}
const rows = ref<any[]>([])
const utmCampaigns = ref<any[]>([])
const bulkRows = ref<any[]>([])
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
  schedule_for: 'Campaign',
  campaign: '',
  recipient_type: 'WA Recipient List',
  recipient: '',
  whatsapp_template: '',
  start_date: '',
  trigger_time: '',
  send_after_days: '0',
  stop_on_reply: false,
})
const campaignForm = ref({
  name: '',
  description: '',
  whatsapp_account: '',
  schedules: [{ whatsapp_template: '', send_after_days: '0', variable_type: 'Common', template_variables: '' }],
})
const campaignEditorOpen = ref(false)
const campaignEditorMode = ref<'create' | 'edit'>('create')
const editingCampaign = ref('')
const recipientTypeOptions = [
  { label: 'Recipient list', value: 'WA Recipient List' },
  { label: 'Profile', value: 'WA Profile' },
]
const scheduleForOptions = [
  { label: 'Campaign', value: 'Campaign' },
  { label: 'WhatsApp template', value: 'Template' },
]
const statusFilterOptions = computed(() => [
  { label: `All (${rows.value.length})`, value: 'all', theme: 'gray' as const },
  { label: 'Scheduled', value: 'Scheduled', theme: 'gray' as const },
  { label: 'In Progress', value: 'In Progress', theme: 'blue' as const },
  { label: 'Completed', value: 'Completed', theme: 'green' as const },
  { label: 'Draft', value: 'Draft', theme: 'gray' as const },
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
  utmCampaigns.value = forAccount(
    demoCampaigns.value.map((row) => ({
      name: row.campaign_name,
      campaign_name: row.campaign_name,
      description: row.description || '',
      whatsapp_account: row.whatsapp_account,
      template: row.template,
      whatsapp_template: row.template,
      send_after_days: row.send_after_days || 0,
    })),
  )
  bulkRows.value = demoCampaigns.value
    .filter((row) => row.sent_count)
    .map((row) => ({
      name: `BULK-${row.name}`,
      title: row.campaign_name,
      campaign: row.campaign_name,
      whatsapp_campaign: row.name,
      status: row.status === 'Completed' ? 'Completed' : 'In Progress',
      sent_count: row.sent_count,
      failed_count: row.failed_count,
      recipient_count: (row.recipients || []).length,
      whatsapp_account: row.whatsapp_account,
      template: row.template,
    }))
  rows.value = forAccount(demoCampaigns.value)
  const current = selected.value && rows.value.find((row) => row.name === selected.value.name)
  selected.value = current || rows.value[0] || null
  selectedCampaign.value = utmCampaigns.value.find((row) => row.name === selectedCampaign.value?.name) || utmCampaigns.value[0] || null
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
    utmCampaigns.value = (await listUtmCampaigns(account).catch(() => [])) || []
    selectedCampaign.value = utmCampaigns.value.find((row) => row.name === selectedCampaign.value?.name) || utmCampaigns.value[0] || null
    bulkRows.value = (await listBulkResults(account).catch(() => [])) || []
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

const currentAccountLabel = computed(() => {
  const match = (desk.inbox.value?.accounts || []).find((row) => row.name === currentAccount.value)
  return match?.account_name || currentAccount.value
})

const templateOptions = computed(() => {
  const account = currentAccount.value
  return (desk.inbox.value?.templates || [])
    .filter((row) => Boolean(account) && row.whatsapp_account === account)
    .map((row) => ({
      label: displayTitle(row.template_label, row.template_name) || 'Untitled template',
      value: row.name,
    }))
})

const recipientListOptions = computed(() => {
  const account = currentAccount.value
  return recipientLists.value
    .filter((row) => Boolean(account) && (!row.whatsapp_account || row.whatsapp_account === account))
    .map((row) => ({
      label: displayTitle(row.list_name) || 'Recipient list',
      value: row.name,
    }))
})

const profileOptions = computed(() => {
  const account = currentAccount.value
  return profiles.value
    .filter((row) => Boolean(account) && (!row.whatsapp_account || row.whatsapp_account === account))
    .map((row) => ({
      label: row.phone_number
        ? `${displayTitle(row.profile_name) || 'Contact'} · ${row.phone_number}`
        : displayTitle(row.profile_name) || 'Contact',
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

function setScheduleFor(value: unknown) {
  const next = String(value || 'Campaign') === 'Template' ? 'Template' : 'Campaign'
  form.value.schedule_for = next
  if (next === 'Template') form.value.campaign = ''
  else form.value.whatsapp_template = ''
}

function blankForm() {
  return {
    name: '',
    description: '',
    whatsapp_account: currentAccount.value,
    schedule_for: 'Campaign',
    campaign: utmCampaigns.value[0]?.name || '',
    recipient_type: 'WA Recipient List',
    recipient: '',
    whatsapp_template: '',
    start_date: '',
    trigger_time: '',
    send_after_days: '0',
    stop_on_reply: false,
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

const scheduleDays = computed(() => {
  if (form.value.schedule_for === 'Template') return 0
  const match = utmCampaigns.value.find((row) => row.name === form.value.campaign)
  return Number(match?.send_after_days || 0)
})

const previewEnd = computed(() => {
  if (!form.value.start_date) return ''
  const start = new Date(`${form.value.start_date}T00:00:00`)
  start.setDate(start.getDate() + scheduleDays.value)
  const month = String(start.getMonth() + 1).padStart(2, '0')
  const day = String(start.getDate()).padStart(2, '0')
  return `${start.getFullYear()}-${month}-${day}`
})

function fillForm(row: any) {
  const schedule = firstSchedule(row)
  const templateMode = row.schedule_source === 'Template'
  form.value = {
    name: row.campaign_name || row.name || '',
    description: row.description || row.campaign_description || '',
    whatsapp_account: currentAccount.value || row.whatsapp_account || '',
    schedule_for: templateMode ? 'Template' : 'Campaign',
    campaign: templateMode ? '' : row.campaign || row.campaign_name || '',
    recipient_type: row.recipient_type || 'WA Recipient List',
    recipient: row.recipient || '',
    whatsapp_template: templateMode ? row.whatsapp_template || row.template || '' : schedule?.whatsapp_template || '',
    start_date: dateOnly(row.start_date),
    trigger_time: timeOnly(row.trigger_time),
    send_after_days: String(schedule?.send_after_days ?? row.send_after_days ?? 0),
    stop_on_reply: Boolean(row.stop_on_reply),
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
    title: 'Delete schedule?',
    message: `Remove the schedule for “${campaign.campaign_name || campaign.template_label || campaign.name}”?`,
    onConfirm: async () => {
      busy.value = true
      try {
        if (live) await deleteCampaign(campaign.name)
        else demoCampaigns.value = demoCampaigns.value.filter((row) => row.name !== campaign.name)
        rows.value = rows.value.filter((row) => row.name !== campaign.name)
        selected.value = null
        toast.success('Schedule deleted')
      } finally {
        busy.value = false
      }
    },
  })
}

async function saveCampaign() {
  form.value.whatsapp_account = currentAccount.value
  if (!form.value.whatsapp_account) {
    toast.error('Select a WhatsApp number in the top bar first.')
    return
  }
  const templateMode = form.value.schedule_for === 'Template'
  const campaign = templateMode ? '' : form.value.campaign
  if (templateMode && !form.value.whatsapp_template) {
    toast.error('Select a WhatsApp template.')
    return
  }
  if (!templateMode && !campaign) {
    toast.error('Select a campaign.')
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
      const templateLabel =
        templateOptions.value.find((option) => option.value === form.value.whatsapp_template)?.label ||
        form.value.whatsapp_template
      const row = {
        name: editorMode.value === 'edit' ? editingName.value : `sched-${Date.now()}`,
        schedule_source: templateMode ? 'Template' : 'Campaign',
        campaign: campaign,
        campaign_name: templateMode ? templateLabel : campaign,
        template_label: templateMode ? templateLabel : '',
        whatsapp_schedules: templateMode
          ? [{ whatsapp_template: form.value.whatsapp_template, template_label: templateLabel, send_after_days: 0, variable_type: 'Common' }]
          : [],
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
        stop_on_reply: form.value.stop_on_reply ? 1 : 0,
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
      toast.success(editorMode.value === 'edit' ? 'Schedule updated' : 'Schedule created')
      return
    }
    const saved =
      editorMode.value === 'edit'
        ? await updateWhatsappSchedule({
            name: editingName.value,
            campaign,
            schedule_for: form.value.schedule_for,
            whatsapp_template: templateMode ? form.value.whatsapp_template : '',
            whatsapp_account: form.value.whatsapp_account,
            recipient_type: form.value.recipient_type,
            recipient: form.value.recipient,
            start_date: form.value.start_date,
            trigger_time: form.value.trigger_time,
            stop_on_reply: form.value.stop_on_reply ? 1 : 0,
          })
        : await createWhatsappSchedule({
            campaign,
            schedule_for: form.value.schedule_for,
            whatsapp_template: templateMode ? form.value.whatsapp_template : '',
            whatsapp_account: form.value.whatsapp_account,
            recipient_type: form.value.recipient_type,
            recipient: form.value.recipient,
            start_date: form.value.start_date,
            trigger_time: form.value.trigger_time,
            stop_on_reply: form.value.stop_on_reply ? 1 : 0,
          })
    editorOpen.value = false
    toast.success(editorMode.value === 'edit' ? 'Schedule updated' : 'Schedule created')
    await load()
    if (saved?.name) selected.value = await getCampaign(saved.name).catch(() => saved)
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    saving.value = false
  }
}

// Top KPI metrics
const campaignOptions = computed(() => {
  const account = currentAccount.value
  return utmCampaigns.value
    .filter((row) => Boolean(account) && row.whatsapp_account === account)
    .map((row) => ({
      label: displayTitle(row.campaign_name) || 'Campaign',
      value: row.name,
    }))
})

const bulkSent = computed(() => bulkRows.value.reduce((sum, row) => sum + Number(row.sent_count || 0), 0))
const bulkFailed = computed(() => bulkRows.value.reduce((sum, row) => sum + Number(row.failed_count || 0), 0))
const bulkRecipients = computed(() => bulkRows.value.reduce((sum, row) => sum + Number(row.recipient_count || 0), 0))

const variableTypeOptions = [
  { label: 'Common', value: 'Common' },
  { label: 'Unique', value: 'Unique' },
]

function blankScheduleRow() {
  return { whatsapp_template: '', send_after_days: '0', variable_type: 'Common', template_variables: '' }
}

function blankCampaignForm() {
  return {
    name: '',
    description: '',
    whatsapp_account: currentAccount.value,
    schedules: [blankScheduleRow()],
  }
}

function addScheduleRow() {
  campaignForm.value.schedules.push(blankScheduleRow())
}

function removeScheduleRow(index: number) {
  campaignForm.value.schedules.splice(index, 1)
  if (!campaignForm.value.schedules.length) addScheduleRow()
}

function scheduleRowsFrom(source: any) {
  const rows = Array.isArray(source?.whatsapp_schedules) ? source.whatsapp_schedules : []
  const mapped = rows
    .map((row: any) => ({
      whatsapp_template: row.whatsapp_template || row.template || '',
      send_after_days: String(row.send_after_days ?? 0),
      variable_type: row.variable_type || 'Common',
      template_variables: typeof row.template_variables === 'string' ? row.template_variables : row.template_variables ? JSON.stringify(row.template_variables) : '',
    }))
    .filter((row: { whatsapp_template: string }) => row.whatsapp_template)
  if (mapped.length) return mapped
  const template = source?.whatsapp_template || source?.template || ''
  if (!template) return [blankScheduleRow()]
  return [{ whatsapp_template: template, send_after_days: String(source?.send_after_days ?? 0), variable_type: 'Common', template_variables: '' }]
}

function startCampaign() {
  campaignEditorMode.value = 'create'
  editingCampaign.value = ''
  campaignForm.value = blankCampaignForm()
  campaignEditorOpen.value = true
}

async function editCampaign(row: any) {
  campaignEditorMode.value = 'edit'
  editingCampaign.value = row.name
  campaignForm.value = {
    name: row.campaign_name || row.name || '',
    description: row.description || row.campaign_description || '',
    whatsapp_account: currentAccount.value || row.whatsapp_account || '',
    schedules: scheduleRowsFrom(row),
  }
  campaignEditorOpen.value = true
  if (!live) return
  try {
    const full = await getUtmCampaign(row.name)
    campaignForm.value = {
      name: full.campaign_name || full.name || '',
      description: full.campaign_description || full.description || '',
      whatsapp_account: full.whatsapp_account || campaignForm.value.whatsapp_account,
      schedules: scheduleRowsFrom(full),
    }
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

async function saveUtmCampaign() {
  campaignForm.value.whatsapp_account = currentAccount.value
  if (!campaignForm.value.whatsapp_account) {
    toast.error('Select a WhatsApp number in the top bar first.')
    return
  }
  const name = campaignForm.value.name.trim()
  if (!name) {
    toast.error('Campaign name is required.')
    return
  }
  const schedules = campaignForm.value.schedules
    .map((row) => ({
      whatsapp_template: String(row.whatsapp_template || '').trim(),
      send_after_days: Number(row.send_after_days || 0),
      variable_type: row.variable_type === 'Unique' ? 'Unique' : 'Common',
      template_variables: row.variable_type === 'Unique' ? '' : String(row.template_variables || '').trim(),
    }))
    .filter((row) => row.whatsapp_template)
  if (!schedules.length) {
    toast.error('Add at least one WhatsApp template.')
    return
  }
  saving.value = true
  try {
    if (!live) {
      const row = {
        name: campaignEditorMode.value === 'edit' ? editingCampaign.value : name,
        campaign_name: name,
        description: campaignForm.value.description.trim(),
        whatsapp_account: currentAccount.value,
        template: schedules[0].whatsapp_template,
        whatsapp_template: schedules[0].whatsapp_template,
        send_after_days: Math.max(...schedules.map((row) => row.send_after_days)),
        whatsapp_schedules: schedules,
      }
      utmCampaigns.value = [row, ...utmCampaigns.value.filter((item) => item.name !== row.name)]
      campaignEditorOpen.value = false
      toast.success(campaignEditorMode.value === 'edit' ? 'Campaign updated' : 'Campaign created')
      return
    }
    const saved =
      campaignEditorMode.value === 'edit'
        ? await updateUtmCampaign({
            name: editingCampaign.value,
            campaign_name: name,
            campaign_description: campaignForm.value.description.trim(),
            whatsapp_account: currentAccount.value || undefined,
            schedules,
          })
        : await createUtmCampaign({
            name,
            campaign_description: campaignForm.value.description.trim(),
            whatsapp_account: currentAccount.value || undefined,
            schedules,
          })
    campaignEditorOpen.value = false
    toast.success(campaignEditorMode.value === 'edit' ? 'Campaign updated' : 'Campaign created')
    await load()
    selectedCampaign.value = saved
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    saving.value = false
  }
}

function removeUtmCampaign(row: any) {
  dialog.danger({
    title: 'Delete campaign?',
    message: `Remove “${row.campaign_name || row.name}”? Delete any schedules that still use it first.`,
    onConfirm: async () => {
      busy.value = true
      try {
        if (live) await deleteUtmCampaign(row.name)
        utmCampaigns.value = utmCampaigns.value.filter((item) => item.name !== row.name)
        if (selectedCampaign.value?.name === row.name) selectedCampaign.value = utmCampaigns.value[0] || null
        toast.success('Campaign deleted')
      } catch (caught) {
        toast.error(errorText(caught))
      } finally {
        busy.value = false
      }
    },
  })
}

const selectedCampaign = ref<any | null>(null)
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
      <div class="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <TabButtons
          :model-value="tab"
          :options="[
            { label: 'Campaigns', value: 'campaigns' },
            { label: 'Schedules', value: 'schedules' },
            { label: 'Results', value: 'results' },
          ]"
          variant="underline"
          @update:model-value="setTab"
        />
        <div class="flex items-center justify-end gap-2">
          <Button
            variant="subtle"
            size="sm"
            icon="lucide-refresh-cw"
            label="Refresh"
            :loading="loading"
            @click="load"
          />
          <Button v-if="isManager && tab === 'campaigns'" variant="solid" theme="green" size="sm" icon-left="lucide-plus" label="New campaign" @click="startCampaign()"/>
          <Button v-else-if="isManager && tab === 'schedules'" variant="solid" theme="green" size="sm" icon-left="lucide-plus" label="New schedule" @click="startCreate()"/>
        </div>
      </div>
    </template>

    <div v-if="tab === 'campaigns'" class="min-h-0 flex-1 overflow-y-auto p-4">
      <div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <NumberCard title="Campaigns" :value="utmCampaigns.length" color="#374151" delta-caption="template and send-after" />
        <NumberCard title="Schedules" :value="rows.length" color="#047857" delta-caption="audiences waiting to send" />
        <NumberCard title="Sent" :value="bulkSent" color="#047857" delta-caption="from bulk messages" />
      </div>
      <DeskEmpty v-if="loading && !utmCampaigns.length" kind="loading" title="Loading campaigns…" />
      <DeskEmpty v-else-if="!utmCampaigns.length" kind="empty" title="No campaigns yet" description="A campaign stores the WhatsApp template and how many days after the start it sends. The audience and the clock live on a schedule.">
        <Button v-if="isManager" variant="solid" theme="green" label="New campaign" icon-left="lucide-plus" @click="startCampaign()" class="mt-4"/>
      </DeskEmpty>
      <div v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <button
          v-for="row in utmCampaigns"
          :key="row.name"
          type="button"
          class="rounded-xl border border-outline-gray-2 bg-surface-base p-4 text-left hover:border-outline-green-3"
          @click="isManager && editCampaign(row)"
        >
          <p class="font-semibold text-ink-gray-9">{{ displayTitle(row.campaign_name) || 'Campaign' }}</p>
          <p class="mt-1 text-xs text-ink-gray-5">{{ displayTitle(row.account_label, row.whatsapp_account) || 'No account' }}</p>
          <p class="mt-3 text-sm text-ink-gray-8">{{ displayTitle(row.template_label, row.template, row.whatsapp_template) || 'No template' }}</p>
          <p class="mt-1 text-xs text-ink-gray-5">Sends {{ row.send_after_days || 0 }} day(s) after the schedule starts</p>
          <div class="mt-3 flex justify-end">
            <Button variant="ghost" size="sm" theme="red" label="Delete" @click.stop="removeUtmCampaign(row)" />
          </div>
        </button>
      </div>
    </div>

    <div v-else-if="tab === 'results'" class="min-h-0 flex-1 overflow-y-auto p-4">
      <div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <NumberCard title="Bulk messages" :value="bulkRows.length" color="#374151" delta-caption="one per send day" />
        <NumberCard title="Recipients" :value="bulkRecipients" color="#047857" delta-caption="subscribed rows only" />
        <NumberCard title="Sent" :value="bulkSent" color="#047857" delta-caption="delivered to WhatsApp" />
        <NumberCard title="Failed" :value="bulkFailed" color="#B91C1C" delta-caption="not accepted" />
      </div>
      <DeskEmpty v-if="loading && !bulkRows.length" kind="loading" title="Loading results…" />
      <DeskEmpty v-else-if="!bulkRows.length" kind="empty" title="No bulk messages yet" description="When a schedule reaches its start date and trigger time, one bulk message is created and each subscribed recipient is sent individually." />
      <ul v-else class="divide-y divide-outline-gray-2 rounded-xl border border-outline-gray-2 bg-surface-base">
        <li v-for="row in bulkRows" :key="row.name" class="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <Badge
                v-if="row.status && row.status !== 'Draft'"
                :label="row.status"
                :theme="row.status === 'Completed' ? 'green' : row.status === 'Failed' ? 'red' : 'blue'"
              />
              <span class="truncate text-sm font-semibold text-ink-gray-9">{{ displayTitle(row.title, row.campaign_label) || 'Bulk message' }}</span>
            </div>
            <p class="mt-1 text-xs text-ink-gray-5">{{ displayTitle(row.campaign_label, row.campaign) || 'No campaign' }} · {{ displayTitle(row.template_label, row.template) || 'No template' }}</p>
          </div>
          <div class="flex gap-6 text-xs text-ink-gray-7">
            <span><strong class="text-ink-gray-9">{{ row.recipient_count || 0 }}</strong> recipients</span>
            <span><strong class="text-emerald-700">{{ row.sent_count || 0 }}</strong> sent</span>
            <span><strong class="text-red-700">{{ row.failed_count || 0 }}</strong> failed</span>
          </div>
        </li>
      </ul>
    </div>

    <template v-else>
    <div class="hidden shrink-0 grid-cols-2 gap-3 border-b border-outline-gray-2 px-4 py-3 sm:grid sm:grid-cols-4">
      <NumberCard title="Schedules" :value="totalCampaignsCount" color="#374151" delta-caption="whatsapp campaigns" />
      <NumberCard title="Recipients" :value="totalRecipients" color="#047857" delta-caption="including unsubscribed" />
      <NumberCard title="Sent" :value="totalSent" color="#047857" delta-caption="from bulk messages" />
      <NumberCard title="Failed" :value="totalFailed" color="#B91C1C" delta-caption="from bulk messages" />
    </div>
    <!-- Content State Handlers -->
    <DeskEmpty v-if="loading && !rows.length" kind="loading" title="Loading schedules…" />
    <DeskEmpty v-else-if="error" kind="error" :message="error" allow-retry @retry="load" />
    <DeskEmpty
      v-else-if="!rows.length"
      kind="empty"
      title="No schedules yet"
      description="Pick a campaign, an audience, a start date, and the time this client should send. Unsubscribed rows are left out of the bulk message."
    >
      <Button variant="solid" theme="green" v-if="isManager" label="New schedule" icon-left="lucide-plus" @click="startCreate()" class="mt-4"/>
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
            placeholder="Search schedules…"
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
              :theme="option.theme"
              :data-state="statusFilter === option.value ? 'active' : undefined"
              :aria-pressed="statusFilter === option.value"
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
            class="flex w-full flex-col gap-2 p-3.5 text-left transition-all hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-green-3"
            :class="
              selected?.name === row.name
                ? 'border-l-4 border-l-green-700 bg-teal-50/70 shadow-2xs'
                : 'border-l-4 border-l-transparent'
            "
            @click="open(row)"
          >
            <div class="flex items-start justify-between gap-2">
              <span class="truncate font-semibold text-sm text-ink-gray-9">
                {{ displayTitle(row.campaign_name) || 'Schedule' }}
              </span>
              <Badge
                v-if="row.status && row.status !== 'Draft'"
                :label="row.status"
                :theme="row.status === 'Completed' ? 'green' : row.status === 'Failed' ? 'red' : row.status === 'In Progress' ? 'blue' : 'gray'"
                size="sm"
              />
            </div>

            <div class="flex items-center gap-2 text-xs text-ink-gray-5">
              <span class="inline-flex items-center gap-1 font-medium text-ink-gray-7">
                <span class="lucide-layout-template size-3 text-ink-green-7" />
                {{ displayTitle(row.template_label, row.template) || 'No template' }}
              </span>
              <span>·</span>
              <span class="truncate">{{ displayTitle(row.account_label, row.whatsapp_account) || 'No account' }}</span>
            </div>

            <!-- Mini Funnel Row -->
            <div class="mt-1 flex items-center justify-between text-[11px] text-ink-gray-5 bg-surface-gray-1/80 rounded px-2 py-1">
              <span class="truncate">{{ displayTitle(row.recipient_label, row.recipient) || 'No audience' }}</span>
              <span>Sent: <strong class="text-ink-gray-8">{{ row.sent_count || 0 }}</strong></span>
              <span v-if="row.failed_count" class="text-red-600 font-semibold">
                {{ row.failed_count }} fail
              </span>
            </div>
          </button>

          <div v-if="filteredRows.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
            No schedules match this search.
          </div>
        </div>
      </template>

      <!-- Right Column: Campaign Inspector & Recipient Audit Funnel -->
      <template #detail>
      <div class="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div v-if="narrow && selected" class="px-4 pt-3">
          <Button variant="ghost" icon-left="lucide-arrow-left" label="All schedules" @click="showDetail = false" />
        </div>
        <!-- Active Campaign Inspector -->
        <div v-if="selected" class="p-5 sm:p-6 space-y-6">
          <!-- Inspector Header -->
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-outline-gray-2 pb-5">
            <div>
              <div class="flex items-center gap-2">
                <Badge
                  v-if="selected.status && selected.status !== 'Draft'"
                  :label="selected.status"
                  :theme="selected.status === 'Completed' ? 'green' : selected.status === 'Failed' ? 'red' : selected.status === 'In Progress' ? 'blue' : 'gray'"
                />
                <span class="text-xs text-ink-gray-5">{{ displayTitle(selected.account_label, selected.whatsapp_account) || 'No account' }}</span>
              </div>
              <h2 class="mt-1.5 text-xl font-bold text-ink-gray-9">
                {{ displayTitle(selected.campaign_name) || 'Schedule' }}
              </h2>
              <p class="text-xs text-ink-gray-5 mt-0.5">
                <span v-if="selected.start_date">
                  {{ formatDay(selected.start_date) }}<span v-if="selected.end_date"> – {{ formatDay(selected.end_date) }}</span>
                </span>
                <span v-if="selected.trigger_time"> · {{ timeOnly(selected.trigger_time) }}</span>
                <span v-if="displayTitle(selected.recipient_label, selected.recipient)"> · {{ displayTitle(selected.recipient_label, selected.recipient) }}</span>
                <span v-if="selected.stop_on_reply"> · stops when a customer replies</span>
              </p>
              <ul v-if="selected.whatsapp_schedules?.length" class="mt-2 space-y-1 text-xs text-ink-gray-7">
                <li v-for="(row, index) in selected.whatsapp_schedules" :key="index">
                  <span class="text-ink-green-7">{{ displayTitle(row.template_label, row.whatsapp_template) || 'Template' }}</span>
                  · day {{ row.send_after_days || 0 }}
                  · {{ row.variable_type || 'Common' }}
                </li>
              </ul>
            </div>

            <div class="flex items-center gap-2 shrink-0">
              <Button v-if="isManager && (selected.status === 'Scheduled' || selected.status === 'In Progress')" variant="solid" theme="green" label="Send bulk message" icon-left="lucide-send" @click="confirmRunOpen = true"/>
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

          <Alert
            v-if="selected.last_error"
            theme="red"
            title="Couldn't complete this schedule"
            :description="formatErrorMessage(selected.last_error)"
            :primary-action="{ label: 'Retry', onClick: () => load() }"
          />

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
            <div class="rounded-xl border border-outline-gray-2 overflow-hidden bg-surface-base">
              <ul class="divide-y divide-outline-gray-1 text-xs">
                <li
                  v-for="rec in filteredRecipients"
                  :key="rec.name || rec.idx || rec.phone_number"
                  class="flex items-center justify-between p-3 hover:bg-surface-gray-1 transition-colors"
                >
                  <div class="flex items-center gap-3 min-w-0">
                    <span class="grid size-8 shrink-0 place-items-center rounded-full bg-teal-100 text-[11px] font-bold text-ink-green-7">
                      {{ initials(rec.profile || rec.phone_number) }}
                    </span>
                    <div class="min-w-0">
                      <p class="font-semibold text-ink-gray-9 truncate">
                        {{ rec.profile || rec.phone_number }}
                      </p>
                      <p class="text-[11px] font-mono text-ink-gray-5">
                        {{ rec.phone_number || rec.profile }}
                      </p>
                      <p v-if="rec.unsubscribed" class="text-[11px] text-ink-gray-6">Unsubscribed</p>
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
            <div class="mx-auto grid size-12 place-items-center rounded-xl bg-teal-50 text-ink-green-7">
              <span class="lucide-megaphone size-6" />
            </div>
            <p class="text-sm font-semibold text-ink-gray-9">Select a schedule</p>
            <p class="text-ink-gray-5 leading-relaxed">
              Click a schedule to see its audience, send window, and who was left out because they unsubscribed.
            </p>
          </div>
        </div>
      </div>
      </template>
    </DeskSplit>
    </template>

    <Dialog v-model="editorOpen" :title="editorMode === 'edit' ? 'Edit schedule' : 'New schedule'">
      <div class="space-y-3 py-1 text-sm">
        <FormControl
          :model-value="form.schedule_for"
          type="select"
          label="Schedule for"
          :options="scheduleForOptions"
          @update:model-value="setScheduleFor"
        />
        <FormControl
          v-if="form.schedule_for === 'Template'"
          v-model="form.whatsapp_template"
          type="select"
          label="WhatsApp template"
          :options="templateOptions"
        />
        <FormControl
          v-else
          v-model="form.campaign"
          type="select"
          label="Campaign"
          :options="campaignOptions"
        />
        <p class="text-xs text-ink-gray-5">
          WhatsApp account: {{ displayTitle(currentAccountLabel) || 'Select a number in the top bar' }}
        </p>
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
        <div class="grid grid-cols-3 gap-3">
          <FormControl v-model="form.start_date" type="date" label="Start date" />
          <FormControl :model-value="previewEnd" type="date" label="End date" disabled />
          <FormControl v-model="form.trigger_time" type="time" label="Trigger time" />
        </div>
        <label class="flex items-start gap-2 text-sm text-ink-gray-8">
          <Checkbox v-model="form.stop_on_reply" class="mt-0.5" />
          <span>
            <span class="font-medium">Stop on customer reply</span>
            <span class="mt-0.5 block text-xs text-ink-gray-5">
              After a step is sent, any reply ticks Unsubscribed for that phone on this campaign and on the recipient list. Later messages are skipped. Nothing is sent back to the customer.
            </span>
          </span>
        </label>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="editorOpen = false" />
          <Button variant="solid" theme="green" loading-text="Saving…" :label="editorMode === 'edit' ? 'Save' : 'Create schedule'" :loading="saving || (editorMode === 'edit' && !recipientsReady)" :disabled="editorMode === 'edit' && !recipientsReady" @click="saveCampaign"/>
        </div>
      </template>
    </Dialog>

    <Dialog v-model="campaignEditorOpen" :title="campaignEditorMode === 'edit' ? 'Edit campaign' : 'New campaign'" size="lg">
      <div class="space-y-3 py-1 text-sm">
        <FormControl v-model="campaignForm.name" type="text" label="Name" placeholder="Festive allocation" required />
        <FormControl v-model="campaignForm.description" type="textarea" label="Description" :rows="3" />
        <p class="text-xs text-ink-gray-5">
          WhatsApp account: {{ displayTitle(currentAccountLabel) || 'Select a number in the top bar' }}
        </p>
        <div class="space-y-2">
          <p class="text-sm font-medium text-ink-gray-8">Templates</p>
          <div class="overflow-hidden rounded-lg border border-outline-gray-2">
            <div class="grid grid-cols-[minmax(0,1fr)_6.5rem_7rem_2rem] gap-2 bg-surface-gray-1 px-3 py-2 text-xs font-medium text-ink-gray-6">
              <span>WhatsApp template</span>
              <span>Send after (days)</span>
              <span>Variables</span>
              <span />
            </div>
            <div
              v-for="(row, index) in campaignForm.schedules"
              :key="index"
              class="space-y-2 border-t border-outline-gray-2 px-3 py-2"
            >
              <div class="grid grid-cols-[minmax(0,1fr)_6.5rem_7rem_2rem] items-center gap-2">
                <FormControl v-model="row.whatsapp_template" type="select" :options="templateOptions" />
                <FormControl v-model="row.send_after_days" type="number" />
                <FormControl v-model="row.variable_type" type="select" :options="variableTypeOptions" />
                <Button variant="ghost" size="sm" icon="lucide-x" aria-label="Remove row" @click="removeScheduleRow(index)" />
              </div>
              <FormControl
                v-if="row.variable_type !== 'Unique'"
                v-model="row.template_variables"
                type="text"
                placeholder='Common variables, for example {"1":"Name"}'
              />
            </div>
            <div class="border-t border-outline-gray-2 px-2 py-1.5">
              <Button variant="ghost" size="sm" label="Add row" icon-left="lucide-plus" @click="addScheduleRow" />
            </div>
          </div>
        </div>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="campaignEditorOpen = false" />
          <Button variant="solid" theme="green" loading-text="Saving…" :label="campaignEditorMode === 'edit' ? 'Save' : 'Create campaign'" :loading="saving" @click="saveUtmCampaign"/>
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
            This creates one bulk message for <strong>{{ displayTitle(selected.campaign_name) || 'this schedule' }}</strong> on <strong>{{ displayTitle(selected.account_label, selected.whatsapp_account) || 'the WhatsApp account' }}</strong>. Each subscribed recipient is sent individually. Unsubscribed numbers are left out.
          </p>
        </div>

        <dl class="divide-y divide-outline-gray-1 border-t border-b border-outline-gray-1 text-xs">
          <div class="flex justify-between py-2">
            <dt class="text-ink-gray-5">WhatsApp Template:</dt>
            <dd class="font-medium text-ink-gray-9">{{ displayTitle(selected.template_label, selected.template) || 'No template' }}</dd>
          </div>
          <div class="flex justify-between py-2">
            <dt class="text-ink-gray-5">Channel Sender Line:</dt>
            <dd class="font-medium text-ink-gray-9">{{ displayTitle(selected.account_label, selected.whatsapp_account) || 'No account' }}</dd>
          </div>
          <div class="flex justify-between py-2">
            <dt class="text-ink-gray-5">Recipients Count:</dt>
            <dd class="font-bold text-ink-green-7">{{ selected.recipients?.length || 0 }} contacts</dd>
          </div>
        </dl>

        <p class="text-[11px] text-ink-gray-5 leading-relaxed">
          Meta WhatsApp Cloud API will charge per delivered marketing template. All recipients must be opted-in.
        </p>
      </div>

      <template #actions>
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="confirmRunOpen = false" />
          <Button variant="solid" theme="green" loading-text="Sending…" label="Create bulk message" icon-left="lucide-send" :loading="busy" @click="run(selected.name)"/>
        </div>
      </template>
    </Dialog>
  </DeskPage>
</template>
