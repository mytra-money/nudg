<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Button, Dialog, toast } from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatDay, formatTime, rawErrorText } from '@/utils/format'
import {
  cancelChatbotSession,
  deleteChatbotFlow,
  deleteChatbotKeyword,
  getChatbot,
  listChatbotFlows,
  listChatbotHandoffs,
  listChatbotKeywords,
  resumeChatbotHandoff,
  saveChatbot,
  saveChatbotFlow,
  saveChatbotKeyword,
} from '@/services/catalogApi'
import { useDesk } from '@/stores/desk'

type Tab = 'bot' | 'keywords' | 'flows' | 'handoffs'

interface HourRow {
  day: string
  enabled: number
  start_time: string
  end_time: string
}

interface FlowStep {
  step_name: string
  message: string
  input_type: string
  store_as: string
}

const desk = useDesk()
const tab = ref<Tab>('bot')
const account = ref('')
const loading = ref(true)
const saving = ref(false)
const error = ref<string | null>(null)

const bot = ref({
  enabled: 0,
  default_response: '',
  business_hours_only: 0,
  out_of_hours_message: '',
  business_hours: [] as HourRow[],
  enable_ai: 0,
  ai_provider: '',
  has_ai_key: 0,
  ai_api_key: '',
  ai_model: '',
  session_timeout_minutes: 30,
  excluded_numbers: '',
})

const keywords = ref<any[]>([])
const flows = ref<any[]>([])
const transfers = ref<any[]>([])
const sessions = ref<any[]>([])

const keywordOpen = ref(false)
const flowOpen = ref(false)
const keywordForm = ref(emptyKeyword())
const flowForm = ref(emptyFlow())

const accounts = computed(() => desk.inbox.value?.accounts || [])
const flowOptions = computed(() => flows.value.map((row) => ({ name: row.name, label: row.flow_name || row.name })))

function emptyKeyword() {
  return {
    name: '',
    keywords: '',
    match_type: 'Contains',
    response_type: 'Text',
    response_text: '',
    trigger_flow: '',
    enabled: 1,
  }
}

function emptyFlow() {
  return {
    name: '',
    flow_name: '',
    trigger_keywords: '',
    initial_message: '',
    completion_message: '',
    cancel_keywords: 'stop',
    enabled: 1,
    steps: [emptyStep(1)] as FlowStep[],
  }
}

function emptyStep(index: number): FlowStep {
  return { step_name: `step_${index}`, message: '', input_type: 'Text', store_as: '' }
}

function clock(value: string) {
  return (value || '').slice(0, 5)
}

async function loadAccount() {
  if (!account.value) return
  loading.value = true
  error.value = null
  try {
    const [settings, keywordRows, flowRows, handoff] = await Promise.all([
      getChatbot(account.value),
      listChatbotKeywords(account.value),
      listChatbotFlows(account.value),
      listChatbotHandoffs(account.value),
    ])
    bot.value = {
      enabled: settings.enabled || 0,
      default_response: settings.default_response || '',
      business_hours_only: settings.business_hours_only || 0,
      out_of_hours_message: settings.out_of_hours_message || '',
      business_hours: (settings.business_hours || []).map((row: HourRow) => ({
        ...row,
        start_time: clock(row.start_time),
        end_time: clock(row.end_time),
      })),
      enable_ai: settings.enable_ai || 0,
      ai_provider: settings.ai_provider || '',
      has_ai_key: settings.has_ai_key || 0,
      ai_api_key: '',
      ai_model: settings.ai_model || '',
      session_timeout_minutes: settings.session_timeout_minutes || 30,
      excluded_numbers: (settings.excluded_numbers || []).join('\n'),
    }
    keywords.value = keywordRows || []
    flows.value = flowRows || []
    transfers.value = handoff?.transfers || []
    sessions.value = handoff?.sessions || []
  } catch (err) {
    error.value = rawErrorText(err)
  } finally {
    loading.value = false
  }
}

async function saveBot() {
  if (!account.value) return
  saving.value = true
  try {
    const saved = await saveChatbot(account.value, {
      ...bot.value,
      excluded_numbers: bot.value.excluded_numbers
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean),
    })
    bot.value.has_ai_key = saved.has_ai_key || 0
    bot.value.ai_api_key = ''
    toast.success('Chatbot saved')
  } catch (err) {
    toast.error(rawErrorText(err))
  } finally {
    saving.value = false
  }
}

function openKeyword(row?: any) {
  keywordForm.value = row
    ? {
        name: row.name,
        keywords: row.keywords || '',
        match_type: row.match_type || 'Contains',
        response_type: row.response_type === 'Flow' ? 'Flow' : 'Text',
        response_text: row.response_text || '',
        trigger_flow: row.trigger_flow || '',
        enabled: row.enabled ? 1 : 0,
      }
    : emptyKeyword()
  keywordOpen.value = true
}

async function saveKeyword() {
  saving.value = true
  try {
    await saveChatbotKeyword(account.value, { ...keywordForm.value })
    keywordOpen.value = false
    keywords.value = (await listChatbotKeywords(account.value)) || []
    toast.success('Keyword saved')
  } catch (err) {
    toast.error(rawErrorText(err))
  } finally {
    saving.value = false
  }
}

async function removeKeyword(name: string) {
  if (!window.confirm('Delete this keyword?')) return
  try {
    await deleteChatbotKeyword(account.value, name)
    keywords.value = keywords.value.filter((row) => row.name !== name)
  } catch (err) {
    toast.error(rawErrorText(err))
  }
}

function openFlow(row?: any) {
  flowForm.value = row
    ? {
        name: row.name,
        flow_name: row.flow_name || row.name,
        trigger_keywords: row.trigger_keywords || '',
        initial_message: row.initial_message || '',
        completion_message: row.completion_message || '',
        cancel_keywords: row.cancel_keywords || 'stop',
        enabled: row.enabled ? 1 : 0,
        steps: (row.steps || []).map((step: FlowStep, index: number) => ({
          step_name: step.step_name || `step_${index + 1}`,
          message: step.message || '',
          input_type: step.input_type || 'Text',
          store_as: step.store_as || '',
        })),
      }
    : emptyFlow()
  if (!flowForm.value.steps.length) flowForm.value.steps = [emptyStep(1)]
  flowOpen.value = true
}

function addStep() {
  flowForm.value.steps.push(emptyStep(flowForm.value.steps.length + 1))
}

function removeStep(index: number) {
  flowForm.value.steps.splice(index, 1)
  if (!flowForm.value.steps.length) flowForm.value.steps.push(emptyStep(1))
}

async function saveFlow() {
  saving.value = true
  try {
    await saveChatbotFlow(account.value, {
      ...flowForm.value,
      steps: flowForm.value.steps.map((step, index) => ({
        ...step,
        step_name: (step.store_as || step.step_name || `step_${index + 1}`).trim().replace(/\s+/g, '_'),
      })),
    })
    flowOpen.value = false
    flows.value = (await listChatbotFlows(account.value)) || []
    toast.success('Flow saved')
  } catch (err) {
    toast.error(rawErrorText(err))
  } finally {
    saving.value = false
  }
}

async function removeFlow(name: string) {
  if (!window.confirm('Delete this flow?')) return
  try {
    await deleteChatbotFlow(account.value, name)
    flows.value = flows.value.filter((row) => row.name !== name)
  } catch (err) {
    toast.error(rawErrorText(err))
  }
}

async function resume(name: string) {
  try {
    await resumeChatbotHandoff(account.value, name)
    transfers.value = transfers.value.map((row) => (row.name === name ? { ...row, status: 'Resumed' } : row))
    toast.success('Bot is answering this chat again')
  } catch (err) {
    toast.error(rawErrorText(err))
  }
}

async function cancelSession(name: string) {
  try {
    await cancelChatbotSession(account.value, name)
    sessions.value = sessions.value.filter((row) => row.name !== name)
    toast.success('Flow stopped')
  } catch (err) {
    toast.error(rawErrorText(err))
  }
}

function when(value?: string) {
  if (!value) return ''
  return `${formatDay(value)} ${formatTime(value)}`.trim()
}

function pickAccount() {
  const names = accounts.value.map((row) => row.name)
  const selected = desk.account.value
  if (selected && selected !== 'all' && names.includes(selected)) {
    account.value = selected
    return
  }
  if (!account.value || !names.includes(account.value)) account.value = names[0] || ''
  if (!account.value) loading.value = false
}

watch(account, () => {
  if (account.value) loadAccount()
})

watch(accounts, () => {
  if (!account.value) pickAccount()
})

onMounted(async () => {
  await desk.load()
  pickAccount()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-surface-gray-2/60">
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-8">
      <div class="flex flex-col gap-4 border-b border-outline-gray-2 pb-6 md:flex-row md:items-center md:justify-between">
        <div class="flex items-center gap-2.5">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#075E54]/10 text-[#075E54]">
            <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4-.8L3 20l1.2-3.6A7.7 7.7 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <div>
            <h1 class="text-2xl font-bold tracking-tight text-ink-gray-9">Automation</h1>
            <p class="text-xs text-ink-gray-6 sm:text-sm">Set up the bot, then add keywords and questions for one WhatsApp number.</p>
          </div>
        </div>
        <label class="block w-full text-xs font-semibold text-ink-gray-7 md:w-72">
          WhatsApp account
          <select v-model="account" class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-sm font-normal text-ink-gray-9">
            <option v-if="!accounts.length" value="">No account connected</option>
            <option v-for="item in accounts" :key="item.name" :value="item.name">
              {{ item.account_name || item.name }}
            </option>
          </select>
        </label>
      </div>

      <div class="mt-6 flex flex-wrap items-center gap-1 border-b border-outline-gray-2 pb-px">
        <button
          v-for="item in [
            { id: 'bot', label: 'Set up bot' },
            { id: 'keywords', label: 'Keywords' },
            { id: 'flows', label: 'Flows' },
            { id: 'handoffs', label: 'Handoffs' },
          ]"
          :key="item.id"
          type="button"
          class="border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors"
          :class="tab === item.id ? 'border-[#128C7E] text-[#075E54]' : 'border-transparent text-ink-gray-6 hover:text-ink-gray-9'"
          @click="tab = item.id as Tab"
        >
          {{ item.label }}
        </button>
      </div>

      <EmptyState
        v-if="!account"
        class="mt-6"
        title="No WhatsApp account connected"
        description="Connect a WhatsApp number before setting up the bot."
      />
      <LoadingState v-else-if="loading" label="Loading automation…" />
      <ErrorState v-else-if="error" class="mt-6" :message="error" allow-retry @retry="loadAccount" />

      <div v-else-if="tab === 'bot'" class="mt-6 space-y-4">
        <div class="grid items-start gap-4 lg:grid-cols-2">
          <section class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-2xs">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 class="text-sm font-bold text-ink-gray-9">Set up the bot</h2>
                <p class="mt-1 text-xs text-ink-gray-5">Turn it on and save the reply used when no keyword or flow matches.</p>
              </div>
              <label class="flex items-center gap-2 text-xs font-semibold text-ink-gray-7">
                <input v-model="bot.enabled" type="checkbox" class="h-4 w-4 rounded border-outline-gray-3" :true-value="1" :false-value="0" />
                {{ bot.enabled ? 'Bot on' : 'Bot off' }}
              </label>
            </div>
            <label class="mt-4 block text-xs font-semibold text-ink-gray-7">
              Default reply
              <textarea v-model="bot.default_response" rows="4" class="mt-1 block w-full resize-y rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="Thanks, we will reply shortly." />
            </label>
            <label class="mt-3 block max-w-[12rem] text-xs font-semibold text-ink-gray-7">
              Forget a chat after
              <span class="mt-1 flex items-center gap-2 font-normal">
                <input v-model.number="bot.session_timeout_minutes" type="number" min="5" class="w-20 rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" />
                minutes
              </span>
            </label>
          </section>

          <section class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-2xs">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 class="text-sm font-bold text-ink-gray-9">Business hours</h2>
                <p class="mt-1 text-xs text-ink-gray-5">Outside these hours the bot sends the away message.</p>
              </div>
              <label class="flex items-center gap-2 text-xs font-semibold text-ink-gray-7">
                <input v-model="bot.business_hours_only" type="checkbox" class="h-4 w-4 rounded border-outline-gray-3" :true-value="1" :false-value="0" />
                Limit
              </label>
            </div>
            <label class="mt-4 block text-xs font-semibold text-ink-gray-7">
              Away message
              <textarea v-model="bot.out_of_hours_message" rows="2" class="mt-1 block w-full resize-y rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="We are closed. We will reply in the morning." />
            </label>
            <div class="mt-3 divide-y divide-outline-gray-1 overflow-hidden rounded-lg border border-outline-gray-2">
              <div class="hidden grid-cols-[7.5rem_4.5rem_minmax(0,1fr)_minmax(0,1fr)] gap-2 bg-surface-gray-1 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-5 sm:grid">
                <span>Day</span>
                <span>Open</span>
                <span>From</span>
                <span>To</span>
              </div>
              <div v-for="row in bot.business_hours" :key="row.day" class="grid grid-cols-1 gap-2 px-3 py-2 sm:grid-cols-[7.5rem_4.5rem_minmax(0,1fr)_minmax(0,1fr)] sm:items-center">
                <span class="text-xs font-semibold text-ink-gray-8">{{ row.day }}</span>
                <label class="flex items-center gap-1.5 text-xs text-ink-gray-6">
                  <input v-model="row.enabled" type="checkbox" class="h-3.5 w-3.5" :true-value="1" :false-value="0" />
                  Open
                </label>
                <label class="block text-[11px] font-medium text-ink-gray-5">
                  <span class="sm:sr-only">From</span>
                  <input v-model="row.start_time" type="time" class="mt-1 w-full rounded-md border border-outline-gray-2 px-2 py-1 text-xs font-normal text-ink-gray-8 sm:mt-0" :disabled="!row.enabled" />
                </label>
                <label class="block text-[11px] font-medium text-ink-gray-5">
                  <span class="sm:sr-only">To</span>
                  <input v-model="row.end_time" type="time" class="mt-1 w-full rounded-md border border-outline-gray-2 px-2 py-1 text-xs font-normal text-ink-gray-8 sm:mt-0" :disabled="!row.enabled" />
                </label>
              </div>
            </div>
          </section>
        </div>

        <section class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-2xs">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-sm font-bold text-ink-gray-9">AI fallback</h2>
              <p class="mt-1 text-xs text-ink-gray-5">Optional. The bot asks the model only after keywords and flows miss.</p>
            </div>
            <label class="flex items-center gap-2 text-xs font-semibold text-ink-gray-7">
              <input v-model="bot.enable_ai" type="checkbox" class="h-4 w-4 rounded border-outline-gray-3" :true-value="1" :false-value="0" />
              On
            </label>
          </div>
          <div v-if="bot.enable_ai" class="mt-4 grid gap-3 sm:grid-cols-3">
            <label class="block text-xs font-semibold text-ink-gray-7">
              Provider
              <select v-model="bot.ai_provider" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal">
                <option value="">Select</option>
                <option>OpenAI</option>
                <option>Anthropic</option>
                <option>Google</option>
                <option>Custom</option>
              </select>
            </label>
            <label class="block text-xs font-semibold text-ink-gray-7">
              Model
              <input v-model="bot.ai_model" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="gpt-4o-mini" />
            </label>
            <label class="block text-xs font-semibold text-ink-gray-7">
              API key
              <input v-model="bot.ai_api_key" type="password" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" :placeholder="bot.has_ai_key ? 'Saved. Type a new key to replace it.' : 'Paste the key'" />
            </label>
          </div>
          <label class="mt-4 block text-xs font-semibold text-ink-gray-7">
            Never reply to
            <textarea v-model="bot.excluded_numbers" rows="2" class="mt-1 block w-full resize-y rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="One phone number per line" />
          </label>
          <div class="mt-4 flex justify-end">
            <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Save bot" :loading="saving" @click="saveBot" />
          </div>
        </section>
      </div>

      <div v-else-if="tab === 'keywords'" class="mt-6">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p class="text-xs text-ink-gray-5">A matching word sends a reply or starts a flow.</p>
          <Button variant="solid" size="sm" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Add keyword" @click="openKeyword()" />
        </div>
        <div class="overflow-x-auto rounded-xl border border-outline-gray-2 bg-white shadow-2xs">
          <EmptyState v-if="!keywords.length" compact title="No keywords yet" description="A matching word sends a reply or starts a flow." />
          <table v-else class="w-full text-left text-sm">
            <thead class="border-b border-outline-gray-2 bg-surface-gray-1 text-xs font-semibold text-ink-gray-5">
              <tr>
                <th class="px-4 py-2.5 font-semibold">Words</th>
                <th class="px-4 py-2.5 font-semibold">Match</th>
                <th class="px-4 py-2.5 font-semibold">Reply</th>
                <th class="w-28 px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in keywords" :key="row.name" class="border-b border-outline-gray-1 last:border-b-0">
                <td class="px-4 py-3 font-medium text-ink-gray-9">{{ row.keywords }}</td>
                <td class="px-4 py-3 text-ink-gray-6">{{ row.match_type }}</td>
                <td class="max-w-xs truncate px-4 py-3 text-ink-gray-7">{{ row.response_type === 'Flow' ? `Flow · ${row.trigger_flow}` : row.response_text }}</td>
                <td class="px-4 py-3 text-right">
                  <button type="button" class="text-xs font-semibold text-[#075E54]" @click="openKeyword(row)">Edit</button>
                  <button type="button" class="ml-3 text-xs font-semibold text-red-600" @click="removeKeyword(row.name)">Delete</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="tab === 'flows'" class="mt-6">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p class="text-xs text-ink-gray-5">Ask a few questions, then send the closing message. Use {email} to repeat a saved answer.</p>
          <Button variant="solid" size="sm" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Add flow" @click="openFlow()" />
        </div>
        <EmptyState v-if="!flows.length" title="No flows yet" description="Ask a few questions, then send a closing message." />
        <div v-else class="grid gap-3 lg:grid-cols-2">
          <article v-for="row in flows" :key="row.name" class="rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="truncate text-sm font-bold text-ink-gray-9">{{ row.flow_name || row.name }}</h2>
                <p class="mt-1 text-xs text-ink-gray-5">Starts on: {{ row.trigger_keywords || 'a keyword that points here' }}</p>
              </div>
              <StatusBadge :label="row.enabled ? 'On' : 'Off'" />
            </div>
            <ol class="mt-3 space-y-1 text-xs text-ink-gray-7">
              <li v-for="(step, index) in row.steps" :key="step.step_name">{{ Number(index) + 1 }}. {{ step.message }}</li>
            </ol>
            <div class="mt-3 flex justify-end gap-3">
              <button type="button" class="text-xs font-semibold text-[#075E54]" @click="openFlow(row)">Edit</button>
              <button type="button" class="text-xs font-semibold text-red-600" @click="removeFlow(row.name)">Delete</button>
            </div>
          </article>
        </div>
      </div>

      <div v-else class="mt-6 grid items-start gap-4 lg:grid-cols-2">
        <section class="rounded-xl border border-outline-gray-2 bg-white shadow-2xs">
          <div class="border-b border-outline-gray-2 px-5 py-4">
            <h2 class="text-sm font-bold text-ink-gray-9">With an agent</h2>
            <p class="mt-1 text-xs text-ink-gray-5">The bot stays quiet until you hand the chat back.</p>
          </div>
          <EmptyState v-if="!transfers.length" compact title="No handoffs" description="The bot stays quiet while an agent has the chat." />
          <ul v-else>
            <li v-for="row in transfers" :key="row.name" class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-1 px-5 py-3 last:border-b-0">
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-ink-gray-9">{{ row.phone_number }}</p>
                <p class="text-xs text-ink-gray-5">{{ row.agent_name || 'Unassigned' }} · {{ row.status }} · {{ when(row.transferred_at) }}</p>
              </div>
              <Button v-if="row.status === 'Active'" variant="subtle" size="sm" label="Resume bot" @click="resume(row.name)" />
            </li>
          </ul>
        </section>
        <section class="rounded-xl border border-outline-gray-2 bg-white shadow-2xs">
          <div class="border-b border-outline-gray-2 px-5 py-4">
            <h2 class="text-sm font-bold text-ink-gray-9">In a flow</h2>
            <p class="mt-1 text-xs text-ink-gray-5">Someone is answering questions. Stop it to let the normal bot reply.</p>
          </div>
          <EmptyState v-if="!sessions.length" compact title="No active flows" description="Stop a flow to let the normal bot reply." />
          <ul v-else>
            <li v-for="row in sessions" :key="row.name" class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-1 px-5 py-3 last:border-b-0">
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-ink-gray-9">{{ row.phone_number }}</p>
                <p class="text-xs text-ink-gray-5">{{ row.current_flow }} · {{ row.current_step }}</p>
              </div>
              <Button variant="subtle" size="sm" label="Stop" @click="cancelSession(row.name)" />
            </li>
          </ul>
        </section>
      </div>
    </div>

    <Dialog v-model="keywordOpen" :title="keywordForm.name ? 'Edit keyword' : 'Add keyword'">
      <div class="space-y-3">
        <label class="block text-xs font-semibold text-ink-gray-7">
          Words, separated by commas
          <input v-model="keywordForm.keywords" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="hello, hi" />
        </label>
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-ink-gray-7">
            Match
            <select v-model="keywordForm.match_type" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal">
              <option>Contains</option>
              <option>Exact</option>
              <option>Starts With</option>
            </select>
          </label>
          <label class="block text-xs font-semibold text-ink-gray-7">
            Then
            <select v-model="keywordForm.response_type" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal">
              <option value="Text">Send a reply</option>
              <option value="Flow">Start a flow</option>
            </select>
          </label>
        </div>
        <label v-if="keywordForm.response_type === 'Text'" class="block text-xs font-semibold text-ink-gray-7">
          Reply
          <textarea v-model="keywordForm.response_text" rows="3" class="mt-1 block w-full resize-y rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" />
        </label>
        <label v-else class="block text-xs font-semibold text-ink-gray-7">
          Flow
          <select v-model="keywordForm.trigger_flow" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal">
            <option value="">Select a flow</option>
            <option v-for="item in flowOptions" :key="item.name" :value="item.name">{{ item.label }}</option>
          </select>
        </label>
        <label class="flex items-center gap-2 text-xs font-semibold text-ink-gray-7">
          <input v-model="keywordForm.enabled" type="checkbox" class="h-4 w-4" :true-value="1" :false-value="0" />
          Enabled
        </label>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="keywordOpen = false" />
          <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Save" :loading="saving" @click="saveKeyword" />
        </div>
      </template>
    </Dialog>

    <Dialog v-model="flowOpen" :title="flowForm.name ? 'Edit flow' : 'Add flow'" size="lg">
      <div class="space-y-3">
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-ink-gray-7">
            Name
            <input v-model="flowForm.flow_name" :disabled="Boolean(flowForm.name)" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal disabled:bg-surface-gray-1" placeholder="Book a demo" />
          </label>
          <label class="block text-xs font-semibold text-ink-gray-7">
            Start words
            <input v-model="flowForm.trigger_keywords" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="book, demo" />
          </label>
        </div>
        <label class="block text-xs font-semibold text-ink-gray-7">
          Opening message
          <input v-model="flowForm.initial_message" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="Sure, a few quick questions." />
        </label>
        <div class="space-y-2">
          <div v-for="(step, index) in flowForm.steps" :key="index" class="rounded-lg border border-outline-gray-2 p-3">
            <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_8rem_auto] sm:items-end">
              <label class="block text-[11px] font-semibold text-ink-gray-5">
                Question
                <input v-model="step.message" class="mt-1 w-full rounded-md border border-outline-gray-2 px-2 py-1.5 text-sm font-normal text-ink-gray-9" placeholder="What is your email?" />
              </label>
              <label class="block text-[11px] font-semibold text-ink-gray-5">
                Answer
                <select v-model="step.input_type" class="mt-1 w-full rounded-md border border-outline-gray-2 px-2 py-1.5 text-sm font-normal text-ink-gray-9">
                  <option>Text</option>
                  <option>Email</option>
                  <option>Phone</option>
                  <option>Number</option>
                </select>
              </label>
              <label class="block text-[11px] font-semibold text-ink-gray-5">
                Save as
                <input v-model="step.store_as" class="mt-1 w-full rounded-md border border-outline-gray-2 px-2 py-1.5 text-sm font-normal text-ink-gray-9" placeholder="email" />
              </label>
              <button type="button" class="text-left text-xs font-semibold text-red-600 sm:mb-2" @click="removeStep(index)">Remove</button>
            </div>
          </div>
        </div>
        <button type="button" class="text-xs font-semibold text-[#075E54]" @click="addStep">Add question</button>
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block text-xs font-semibold text-ink-gray-7">
            Closing message
            <input v-model="flowForm.completion_message" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="Booked for {email}" />
          </label>
          <label class="block text-xs font-semibold text-ink-gray-7">
            Cancel words
            <input v-model="flowForm.cancel_keywords" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 text-sm font-normal" placeholder="stop, cancel" />
          </label>
        </div>
        <label class="flex items-center gap-2 text-xs font-semibold text-ink-gray-7">
          <input v-model="flowForm.enabled" type="checkbox" class="h-4 w-4" :true-value="1" :false-value="0" />
          Enabled
        </label>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="flowOpen = false" />
          <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Save" :loading="saving" @click="saveFlow" />
        </div>
      </template>
    </Dialog>
  </div>
</template>
