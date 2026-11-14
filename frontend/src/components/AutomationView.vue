<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, Dialog, Select, TextInput, toast } from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { errorText, formatDay, formatTime, initials } from '@/format'
import { formatErrorMessage } from '@/errors'
import { createAutomationRule, deskForm, listAutomationRules, listAutomationRuns, updateAutomationRule } from '@/phase2'
import { isManager, useDesk } from '@/desk'

const desk = useDesk()
const live = Boolean(window.csrf_token)

const loading = ref(true)
const error = ref<string | null>(null)
const rules = ref<any[]>([])
const runs = ref<any[]>([])

const query = ref('')
const selectedTab = ref<'all' | 'active_rules' | 'runs' | 'failed_runs'>('all')
const accountFilter = ref('all')

const selectedRule = ref<any | null>(null)
const ruleDialogOpen = ref(false)

const selectedRun = ref<any | null>(null)
const runDialogOpen = ref(false)
const editorOpen = ref(false)
const editorMode = ref<'create' | 'edit'>('create')
const editingName = ref('')
const saving = ref(false)
const form = ref({
  rule_name: '',
  trigger: 'Incoming Message',
  action: 'Send Text',
  action_reference: '',
  whatsapp_account: '',
  status: 'Active',
})

const triggerOptions = [
  { label: 'Incoming Message', value: 'Incoming Message' },
  { label: 'Status Failed', value: 'Status Failed' },
  { label: 'Window Closed', value: 'Window Closed' },
  { label: 'Keyword Match', value: 'Keyword Match' },
  { label: 'Keyword Rule', value: 'Keyword Rule' },
  { label: 'Out of Office', value: 'Out of Office' },
]
const actionOptions = [
  { label: 'Send Template', value: 'Send Template' },
  { label: 'Assign', value: 'Assign' },
  { label: 'Quick Reply', value: 'Quick Reply' },
  { label: 'Send Text', value: 'Send Text' },
]
const ruleStatusOptions = [
  { label: 'Active', value: 'Active' },
  { label: 'Inactive', value: 'Inactive' },
]

const sampleRules: any[] = [
  {
    name: 'rule-welcome-01',
    rule_name: 'Instant Welcome Greeting',
    trigger: 'First Incoming Message',
    action: 'Send Auto Reply',
    action_reference: 'Hello! Welcome to Sundarban Spices. An agent has been assigned to your query.',
    status: 'Active',
    whatsapp_account: 'Sundarban Sales',
    modified: new Date(Date.now() - 3600000 * 48).toISOString(),
  },
  {
    name: 'rule-dispatch-02',
    rule_name: 'Delivery Note Auto-Notification',
    trigger: 'Delivery Note Submitted',
    action: 'Send WhatsApp Template',
    action_reference: 'dispatch_notice',
    status: 'Active',
    whatsapp_account: 'Sundarban Dispatch',
    modified: new Date(Date.now() - 3600000 * 24).toISOString(),
  },
  {
    name: 'rule-after-hours-03',
    rule_name: 'Out-of-Hours Auto-Responder',
    trigger: 'After Business Hours (7PM - 9AM)',
    action: 'Send Auto Reply',
    action_reference: 'Thank you for contacting us! Our team is currently offline. We will reply at 9:00 AM.',
    status: 'Active',
    whatsapp_account: 'Sundarban Sales',
    modified: new Date(Date.now() - 3600000 * 12).toISOString(),
  },
  {
    name: 'rule-vip-assign-04',
    rule_name: 'VIP Customer Priority Routing',
    trigger: 'Incoming Message (VIP Tag)',
    action: 'Assign to Agent',
    action_reference: 'sales-lead@sundarban.com',
    status: 'Inactive',
    whatsapp_account: 'Sundarban Sales',
    modified: new Date().toISOString(),
  },
]

const sampleRuns: any[] = [
  {
    name: 'run-101',
    rule: 'Instant Welcome Greeting',
    profile: 'Meera Iyer (+91 98450 22119)',
    status: 'Success',
    started_at: new Date(Date.now() - 60000 * 18).toISOString(),
    finished_at: new Date(Date.now() - 60000 * 18 + 420).toISOString(),
    detail: 'Triggered by inbound message wamid.meera.3. Auto-reply delivered in 420ms.',
    reference_message: 'wamid.meera.3',
  },
  {
    name: 'run-102',
    rule: 'Delivery Note Auto-Notification',
    profile: 'Rafiq Traders (+91 33 4065 1180)',
    status: 'Success',
    started_at: new Date(Date.now() - 3600000 * 2).toISOString(),
    finished_at: new Date(Date.now() - 3600000 * 2 + 650).toISOString(),
    detail: 'Delivery Note MAT-DN-0194 submitted in ERPNext. Sent dispatch_notice template.',
    reference_message: 'wamid.rafiq.2',
  },
  {
    name: 'run-103',
    rule: 'Out-of-Hours Auto-Responder',
    profile: 'Anita Desai (+91 98200 44110)',
    status: 'Success',
    started_at: new Date(Date.now() - 3600000 * 11).toISOString(),
    finished_at: new Date(Date.now() - 3600000 * 11 + 310).toISOString(),
    detail: 'Customer message received at 11:24 PM. Sent offline business hours notification.',
    reference_message: 'wamid.anita.1',
  },
  {
    name: 'run-104',
    rule: 'VIP Customer Priority Routing',
    profile: 'Hotel Grand Chowringhee (+91 33 2223 8890)',
    status: 'Failed',
    started_at: new Date(Date.now() - 3600000 * 26).toISOString(),
    finished_at: new Date(Date.now() - 3600000 * 26 + 120).toISOString(),
    detail: 'Execution failed: Customer profile is marked as Blocked / Opted-Out. Routing aborted.',
    reference_message: 'wamid.hotel.fail',
  },
]

async function load() {
  loading.value = true
  error.value = null
  try {
    if (!live) {
      rules.value = sampleRules
      runs.value = sampleRuns
      return
    }
    const [fetchedRules, fetchedRuns] = await Promise.all([
      listAutomationRules().catch(() => []),
      listAutomationRuns().catch(() => []),
    ])
    rules.value = fetchedRules || []
    runs.value = fetchedRuns || []
  } catch (caught) {
    if (!live) {
      rules.value = sampleRules
      runs.value = sampleRuns
    } else {
      error.value = errorText(caught)
    }
  } finally {
    loading.value = false
  }
}

const ruleAccountOptions = computed(() =>
  (desk.inbox.value?.accounts || []).map((row) => ({
    label: row.account_name || row.name,
    value: row.name,
  })),
)

function openDesk(name?: string) {
  window.location.href = deskForm('WhatsApp Automation Rule', name)
}

function startCreate() {
  editorMode.value = 'create'
  editingName.value = ''
  form.value = {
    rule_name: '',
    trigger: 'Incoming Message',
    action: 'Send Text',
    action_reference: '',
    whatsapp_account: ruleAccountOptions.value[0]?.value || '',
    status: 'Active',
  }
  editorOpen.value = true
}

function startEdit(rule: any) {
  editorMode.value = 'edit'
  editingName.value = rule.name
  form.value = {
    rule_name: rule.rule_name || rule.name || '',
    trigger: rule.trigger || 'Incoming Message',
    action: rule.action || 'Send Text',
    action_reference: rule.action_reference || '',
    whatsapp_account: rule.whatsapp_account || '',
    status: rule.status || 'Active',
  }
  ruleDialogOpen.value = false
  editorOpen.value = true
}

async function saveRule() {
  const ruleName = form.value.rule_name.trim()
  if (!ruleName) {
    toast.error('Rule name is required.')
    return
  }
  saving.value = true
  try {
    if (!live) {
      const row = {
        name: editorMode.value === 'edit' ? editingName.value || ruleName : ruleName,
        rule_name: ruleName,
        trigger: form.value.trigger,
        action: form.value.action,
        action_reference: form.value.action_reference.trim(),
        whatsapp_account: form.value.whatsapp_account,
        status: form.value.status,
        modified: new Date().toISOString(),
      }
      if (editorMode.value === 'edit') {
        const index = rules.value.findIndex((item) => item.name === editingName.value)
        if (index >= 0) rules.value[index] = { ...rules.value[index], ...row }
      } else {
        rules.value = [row, ...rules.value]
      }
      editorOpen.value = false
      toast.success(editorMode.value === 'edit' ? 'Rule updated' : 'Rule created')
      return
    }
    const saved =
      editorMode.value === 'edit'
        ? await updateAutomationRule({
            name: editingName.value,
            rule_name: ruleName,
            trigger: form.value.trigger,
            action: form.value.action,
            action_reference: form.value.action_reference.trim(),
            whatsapp_account: form.value.whatsapp_account || undefined,
            status: form.value.status,
          })
        : await createAutomationRule({
            rule_name: ruleName,
            trigger: form.value.trigger,
            action: form.value.action,
            action_reference: form.value.action_reference.trim(),
            whatsapp_account: form.value.whatsapp_account || undefined,
            status: form.value.status,
          })
    editorOpen.value = false
    toast.success(editorMode.value === 'edit' ? 'Rule updated' : 'Rule created')
    await load()
    if (saved?.name) selectedRule.value = rules.value.find((item) => item.name === saved.name) || saved
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    saving.value = false
  }
}

function inspectRule(rule: any) {
  selectedRule.value = rule
  ruleDialogOpen.value = true
}

function inspectRun(run: any) {
  selectedRun.value = run
  runDialogOpen.value = true
}

// KPI Metrics
const countTotalRules = computed(() => rules.value.length)
const countActiveRules = computed(() => rules.value.filter((r) => r.status === 'Active').length)
const countTotalRuns = computed(() => runs.value.length)
const countSuccessRuns = computed(() => runs.value.filter((r) => r.status === 'Success').length)
const countFailedRuns = computed(() => runs.value.filter((r) => r.status === 'Failed').length)

const successRate = computed(() => {
  if (countTotalRuns.value === 0) return 100
  return Math.round((countSuccessRuns.value / countTotalRuns.value) * 100)
})

// Account Options
const accountOptions = computed(() => {
  const accs = desk.inbox.value?.accounts || []
  return [
    { label: 'All Accounts', value: 'all' },
    ...accs.map((a) => ({ label: a.account_name || a.name, value: a.name })),
  ]
})

// Filtered Rules
const filteredRules = computed(() => {
  return rules.value.filter((row) => {
    if (selectedTab.value === 'active_rules' && row.status !== 'Active') return false
    if (accountFilter.value !== 'all' && row.whatsapp_account && row.whatsapp_account !== accountFilter.value) {
      return false
    }
    if (!query.value.trim()) return true
    const term = query.value.toLowerCase()
    return (
      (row.rule_name || '').toLowerCase().includes(term) ||
      (row.trigger || '').toLowerCase().includes(term) ||
      (row.action || '').toLowerCase().includes(term) ||
      (row.action_reference || '').toLowerCase().includes(term)
    )
  })
})

// Filtered Runs
const filteredRuns = computed(() => {
  return runs.value.filter((row) => {
    if (selectedTab.value === 'failed_runs' && row.status !== 'Failed') return false
    if (!query.value.trim()) return true
    const term = query.value.toLowerCase()
    return (
      (row.rule || '').toLowerCase().includes(term) ||
      (row.profile || '').toLowerCase().includes(term) ||
      (row.detail || '').toLowerCase().includes(term)
    )
  })
})

function clearFilters() {
  query.value = ''
  selectedTab.value = 'all'
  accountFilter.value = 'all'
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
            Automation Engine
          </span>
          <span class="text-xs text-ink-gray-5">·</span>
          <span class="text-xs font-medium text-ink-gray-6">Triggers & Webhook Rules</span>
        </div>
        <h1 class="mt-1 text-xl font-bold tracking-tight text-ink-gray-9">
          WhatsApp Automation & Workflows
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
          label="New Rule"
          @click="openDesk()"
        />
      </div>
    </header>

    <!-- Top KPI Performance Bar -->
    <section class="border-b border-outline-gray-2 bg-white px-4 py-3 shrink-0">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <!-- Metric 1: Active Rules -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Active Rules</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-[#075E54]">{{ countActiveRules }}</span>
            <span class="text-[11px] text-ink-gray-5">/ {{ countTotalRules }} configured</span>
          </div>
        </div>

        <!-- Metric 2: Total Executions -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Runs Executed</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-ink-gray-9">{{ countTotalRuns }}</span>
            <span class="text-[11px] text-ink-gray-5">triggers fired</span>
          </div>
        </div>

        <!-- Metric 3: Success Rate -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Execution Success</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold text-emerald-700">{{ successRate }}%</span>
            <span class="text-[11px] text-emerald-600 font-medium">({{ countSuccessRuns }} passed)</span>
          </div>
        </div>

        <!-- Metric 4: Failed Runs -->
        <div class="rounded-lg border border-outline-gray-2 bg-surface-gray-1/50 p-2.5">
          <span class="text-[11px] font-medium uppercase tracking-wider text-ink-gray-5">Trigger Issues</span>
          <div class="mt-1 flex items-baseline gap-1.5">
            <span class="text-xl font-bold" :class="countFailedRuns ? 'text-red-700' : 'text-ink-gray-6'">
              {{ countFailedRuns }}
            </span>
            <span class="text-[11px]" :class="countFailedRuns ? 'text-red-600' : 'text-ink-gray-5'">
              {{ countFailedRuns ? 'requires review' : 'all nominal' }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- Toolbar: Search & Segment Tabs -->
    <section class="border-b border-outline-gray-2 bg-white px-4 py-2.5 space-y-2 shrink-0">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
        <!-- Search Input -->
        <div class="relative flex-1 max-w-sm">
          <TextInput
            v-model="query"
            placeholder="Search rules, triggers, actions, or runs…"
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
          <!-- Segment Tabs -->
          <div class="flex items-center gap-1 rounded-lg bg-surface-gray-2 p-0.5 text-xs">
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedTab === 'all' ? 'bg-white text-ink-gray-9 shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedTab = 'all'"
            >
              All Rules & Runs
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedTab === 'active_rules' ? 'bg-white text-[#075E54] shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedTab = 'active_rules'"
            >
              Active Rules ({{ countActiveRules }})
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedTab === 'runs' ? 'bg-white text-blue-700 shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedTab = 'runs'"
            >
              Runs Log ({{ countTotalRuns }})
            </button>
            <button
              type="button"
              class="rounded-md px-2.5 py-1 font-medium transition-colors"
              :class="selectedTab === 'failed_runs' ? 'bg-white text-red-700 shadow-xs' : 'text-ink-gray-6 hover:text-ink-gray-9'"
              @click="selectedTab = 'failed_runs'"
            >
              Failed Runs ({{ countFailedRuns }})
            </button>
          </div>

          <!-- Channel Filter -->
          <Select
            class="w-36 text-xs"
            :model-value="accountFilter"
            :options="accountOptions"
            @update:model-value="(val) => (accountFilter = String(val || 'all'))"
          />
        </div>
      </div>
    </section>

    <!-- Content State Handlers -->
    <LoadingState v-if="loading && !rules.length" label="Loading automation workflows…" />
    <ErrorState v-else-if="error" :message="error" allow-retry @retry="load" />

    <!-- Two-Column Master-Detail Automation Canvas -->
    <div v-else class="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-outline-gray-2 overflow-hidden">
      <!-- Left Column: Automation Rules -->
      <section class="flex flex-col min-h-0 bg-white overflow-hidden" aria-labelledby="rules-heading">
        <div class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-3 bg-surface-gray-1/40">
          <div class="flex items-center gap-2">
            <span class="lucide-workflow size-4 text-[#075E54]" />
            <h2 id="rules-heading" class="text-xs font-bold uppercase tracking-wider text-ink-gray-8">
              Configured Rules ({{ filteredRules.length }})
            </h2>
          </div>
          <span class="text-[11px] text-ink-gray-5">Evaluated on webhook events</span>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto divide-y divide-outline-gray-1">
          <div v-if="filteredRules.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
            <div class="mx-auto grid size-10 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-4">
              <span class="lucide-workflow size-5" />
            </div>
            <p class="mt-2 text-sm font-semibold text-ink-gray-8">No automation rules found</p>
            <p class="mt-1 text-ink-gray-5">Create a rule here to automate replies or notifications.</p>
            <button
              v-if="isManager"
              type="button"
              class="mt-3 text-xs font-semibold text-[#075E54] hover:underline"
              @click="openDesk()"
            >
              New rule
            </button>
          </div>

          <div
            v-for="row in filteredRules"
            :key="row.name"
            class="flex flex-col gap-2 p-4 transition-all hover:bg-surface-gray-1"
          >
            <!-- Rule Title & Status -->
            <div class="flex items-start justify-between gap-2">
              <div>
                <p class="text-sm font-bold text-ink-gray-9 leading-tight">
                  {{ row.rule_name }}
                </p>
                <p v-if="row.whatsapp_account" class="text-[11px] font-mono text-ink-gray-5 mt-0.5">
                  Channel: {{ row.whatsapp_account }}
                </p>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <Badge :label="row.status" :theme="row.status === 'Active' ? 'green' : 'gray'" size="sm" />
                <button
                  type="button"
                  class="rounded p-1 text-ink-gray-4 hover:bg-surface-gray-2 hover:text-[#075E54]"
                  title="Inspect Rule Details"
                  @click="inspectRule(row)"
                >
                  <span class="lucide-eye size-3.5" />
                </button>
              </div>
            </div>

            <!-- Workflow Pipeline Badges -->
            <div class="flex flex-wrap items-center gap-1.5 text-xs pt-1">
              <span class="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 font-medium text-amber-800 text-[11px]">
                <span class="lucide-zap size-3" />
                Trigger: {{ row.trigger }}
              </span>
              <span class="text-ink-gray-4 font-bold">&rarr;</span>
              <span class="inline-flex items-center gap-1 rounded bg-teal-50 px-2 py-0.5 font-medium text-[#075E54] text-[11px]">
                <span class="lucide-play-circle size-3" />
                Action: {{ row.action }}
              </span>
            </div>

            <!-- Action Reference / Content Preview -->
            <p v-if="row.action_reference" class="text-xs text-ink-gray-6 italic line-clamp-2 bg-surface-gray-1/70 rounded p-2 mt-1">
              "{{ row.action_reference }}"
            </p>

            <!-- Bottom Row: Modified Date & Actions -->
            <div class="flex items-center justify-between text-[11px] text-ink-gray-5 pt-1">
              <span>Updated {{ formatDay(row.modified) }}</span>
              <button
                v-if="isManager"
                type="button"
                class="font-medium text-[#075E54] hover:underline"
                @click="openDesk(row.name)"
              >
                Edit in Desk
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Right Column: Live Execution Runs & Log Stream -->
      <section class="flex flex-col min-h-0 bg-white overflow-hidden" aria-labelledby="runs-heading">
        <div class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-3 bg-surface-gray-1/40">
          <div class="flex items-center gap-2">
            <span class="lucide-history size-4 text-blue-600" />
            <h2 id="runs-heading" class="text-xs font-bold uppercase tracking-wider text-ink-gray-8">
              Live Execution Audit Runs ({{ filteredRuns.length }})
            </h2>
          </div>
          <span class="text-[11px] text-ink-gray-5">Real-time webhook log</span>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto divide-y divide-outline-gray-1">
          <div v-if="filteredRuns.length === 0" class="p-8 text-center text-xs text-ink-gray-5">
            <div class="mx-auto grid size-10 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-4">
              <span class="lucide-history size-5" />
            </div>
            <p class="mt-2 text-sm font-semibold text-ink-gray-8">No execution runs recorded</p>
            <p class="mt-1 text-ink-gray-5">Runs appear automatically whenever incoming messages trigger active rules.</p>
          </div>

          <div
            v-for="row in filteredRuns"
            :key="row.name"
            class="flex flex-col gap-2 p-4 transition-all hover:bg-surface-gray-1"
          >
            <!-- Run Header -->
            <div class="flex items-start justify-between gap-2">
              <div class="flex items-center gap-2 min-w-0">
                <span
                  class="size-2 rounded-full shrink-0"
                  :class="row.status === 'Success' ? 'bg-emerald-500' : 'bg-red-500'"
                />
                <span class="font-bold text-sm text-ink-gray-9 truncate">
                  {{ row.rule }}
                </span>
              </div>
              <Badge
                :label="row.status"
                :theme="row.status === 'Success' ? 'green' : row.status === 'Failed' ? 'red' : 'gray'"
                size="sm"
              />
            </div>

            <!-- Profile & Timestamp -->
            <div class="flex items-center justify-between text-xs text-ink-gray-6">
              <div class="flex items-center gap-2 min-w-0">
                <span class="grid size-6 shrink-0 place-items-center rounded-full bg-teal-100 text-[10px] font-bold text-[#075E54]">
                  {{ initials(row.profile) }}
                </span>
                <span class="font-medium text-ink-gray-9 truncate">{{ row.profile }}</span>
              </div>
              <span class="text-[11px] text-ink-gray-5 shrink-0 font-mono">
                {{ formatDay(row.started_at) }} · {{ formatTime(row.started_at) }}
              </span>
            </div>

            <!-- Detail Execution Log Message -->
            <div class="rounded-lg bg-surface-gray-1 p-2.5 text-xs text-ink-gray-7 leading-relaxed">
              <p>{{ row.detail }}</p>
              <div v-if="row.reference_message" class="mt-1 text-[11px] font-mono text-ink-gray-5">
                Ref Message: {{ row.reference_message }}
              </div>
            </div>

            <div class="flex justify-end pt-0.5">
              <button
                type="button"
                class="text-[11px] font-medium text-[#075E54] hover:underline"
                @click="inspectRun(row)"
              >
                Inspect Payload &rarr;
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <Dialog v-model="editorOpen" :title="editorMode === 'edit' ? 'Edit rule' : 'New rule'">
      <div class="space-y-3 py-1 text-sm">
        <label class="block text-xs font-medium text-ink-gray-7">
          Rule name
          <TextInput v-model="form.rule_name" class="mt-1" placeholder="After-hours reply" />
        </label>
        <label class="block text-xs font-medium text-ink-gray-7">
          Trigger
          <Select
            class="mt-1"
            :model-value="form.trigger"
            :options="triggerOptions"
            @update:model-value="(val) => (form.trigger = String(val || 'Incoming Message'))"
          />
        </label>
        <label class="block text-xs font-medium text-ink-gray-7">
          Action
          <Select
            class="mt-1"
            :model-value="form.action"
            :options="actionOptions"
            @update:model-value="(val) => (form.action = String(val || 'Send Text'))"
          />
        </label>
        <label class="block text-xs font-medium text-ink-gray-7">
          Action reference
          <TextInput v-model="form.action_reference" class="mt-1" placeholder="Template, user, quick reply, or message text" />
        </label>
        <label class="block text-xs font-medium text-ink-gray-7">
          WhatsApp account
          <Select
            class="mt-1"
            :model-value="form.whatsapp_account"
            :options="ruleAccountOptions"
            @update:model-value="(val) => (form.whatsapp_account = String(val || ''))"
          />
        </label>
        <label class="block text-xs font-medium text-ink-gray-7">
          Status
          <Select
            class="mt-1"
            :model-value="form.status"
            :options="ruleStatusOptions"
            @update:model-value="(val) => (form.status = String(val || 'Active'))"
          />
        </label>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button label="Cancel" @click="editorOpen = false" />
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            :label="editorMode === 'edit' ? 'Save' : 'Create rule'"
            :loading="saving"
            @click="saveRule"
          />
        </div>
      </template>
    </Dialog>

    <!-- Rule Inspector Modal Dialog -->
    <Dialog v-model="ruleDialogOpen" title="Automation Rule Specification" size="xl">
      <div v-if="selectedRule" class="space-y-4 py-2 text-xs">
        <div class="flex items-center justify-between border-b border-outline-gray-2 pb-3">
          <div>
            <h3 class="text-base font-bold text-ink-gray-9">{{ selectedRule.rule_name }}</h3>
            <p class="font-mono text-ink-gray-5">{{ selectedRule.name }}</p>
          </div>
          <Badge :label="selectedRule.status" :theme="selectedRule.status === 'Active' ? 'green' : 'gray'" />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="rounded-lg border border-outline-gray-2 p-3 bg-white">
            <span class="text-ink-gray-5 block text-[10px] font-bold uppercase">Trigger Condition</span>
            <p class="mt-1 font-semibold text-ink-gray-9">{{ selectedRule.trigger }}</p>
          </div>
          <div class="rounded-lg border border-outline-gray-2 p-3 bg-white">
            <span class="text-ink-gray-5 block text-[10px] font-bold uppercase">Action Dispatched</span>
            <p class="mt-1 font-semibold text-[#075E54]">{{ selectedRule.action }}</p>
          </div>
        </div>

        <div v-if="selectedRule.action_reference" class="rounded-lg border border-outline-gray-2 p-3 bg-white">
          <span class="text-ink-gray-5 block text-[10px] font-bold uppercase mb-1">Action Payload / Template Reference</span>
          <p class="text-xs text-ink-gray-8 font-mono bg-surface-gray-1 p-2 rounded whitespace-pre-wrap">
            {{ selectedRule.action_reference }}
          </p>
        </div>

        <div class="rounded-lg border border-outline-gray-2 p-3 bg-white">
          <span class="text-ink-gray-5 block text-[10px] font-bold uppercase mb-1">Sender WhatsApp Channel</span>
          <p class="font-medium text-ink-gray-9">{{ selectedRule.whatsapp_account || 'Default Sender Line' }}</p>
        </div>
      </div>

      <template #actions>
        <div class="flex justify-between w-full">
          <Button
            v-if="isManager"
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Edit Rule in Desk"
            icon-left="lucide-pencil"
            @click="openDesk(selectedRule.name)"
          />
          <Button label="Close" @click="ruleDialogOpen = false" />
        </div>
      </template>
    </Dialog>

    <!-- Run Inspector Modal Dialog -->
    <Dialog v-model="runDialogOpen" title="Execution Run Audit Log" size="xl">
      <div v-if="selectedRun" class="space-y-4 py-2 text-xs">
        <div class="flex items-center justify-between border-b border-outline-gray-2 pb-3">
          <div>
            <h3 class="text-base font-bold text-ink-gray-9">{{ selectedRun.rule }}</h3>
            <p class="font-mono text-ink-gray-5">{{ selectedRun.name }}</p>
          </div>
          <Badge
            :label="selectedRun.status"
            :theme="selectedRun.status === 'Success' ? 'green' : selectedRun.status === 'Failed' ? 'red' : 'gray'"
          />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="rounded-lg border border-outline-gray-2 p-3 bg-white">
            <span class="text-ink-gray-5 block text-[10px] font-bold uppercase">Customer Profile</span>
            <p class="mt-1 font-semibold text-ink-gray-9">{{ selectedRun.profile }}</p>
          </div>
          <div class="rounded-lg border border-outline-gray-2 p-3 bg-white">
            <span class="text-ink-gray-5 block text-[10px] font-bold uppercase">Timestamp</span>
            <p class="mt-1 font-mono text-ink-gray-8">
              {{ formatDay(selectedRun.started_at) }} · {{ formatTime(selectedRun.started_at) }}
            </p>
          </div>
        </div>

        <div class="rounded-lg border border-outline-gray-2 p-3 bg-white">
          <span class="text-ink-gray-5 block text-[10px] font-bold uppercase mb-1">Execution Detail</span>
          <p class="text-xs text-ink-gray-8 leading-relaxed">
            {{ selectedRun.detail }}
          </p>
        </div>

        <div v-if="selectedRun.reference_message" class="rounded-lg border border-outline-gray-2 p-3 bg-white">
          <span class="text-ink-gray-5 block text-[10px] font-bold uppercase mb-1">Linked WA Message ID</span>
          <p class="font-mono text-xs text-[#075E54]">{{ selectedRun.reference_message }}</p>
        </div>
      </div>

      <template #actions>
        <Button label="Close" @click="runDialogOpen = false" />
      </template>
    </Dialog>
  </div>
</template>
