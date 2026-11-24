<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Button, Checkbox, Dialog, FormControl, Switch, TabButtons, TimePicker, dialog, toast } from 'frappe-ui'
import DeskCard from '@/components/desk/DeskCard.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatDay, formatTime, rawErrorText } from '@/utils/format'
import { displayTitle } from '@/utils/titles'
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
import { useAccountGate } from '@/composables/useAccountGate'

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

const tab = ref<Tab>('bot')
const account = ref('')
const { desk, accounts, accountGateDescription, syncAccount } = useAccountGate({ account })
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

const flowOptions = computed(() => flows.value.map((row) => ({ name: row.name, label: row.flow_name || row.name })))

const tabOptions: { value: Tab; label: string }[] = [
  { value: 'bot', label: 'Set up bot' },
  { value: 'keywords', label: 'Keywords' },
  { value: 'flows', label: 'Flows' },
  { value: 'handoffs', label: 'Handoffs' },
]
const providerOptions = [
  { label: 'Select', value: '' },
  { label: 'OpenAI', value: 'OpenAI' },
  { label: 'Anthropic', value: 'Anthropic' },
  { label: 'Google', value: 'Google' },
  { label: 'Custom', value: 'Custom' },
]
const matchTypeOptions = ['Contains', 'Exact', 'Starts With'].map((value) => ({ label: value, value }))
const responseTypeOptions = [
  { label: 'Send a reply', value: 'Text' },
  { label: 'Start a flow', value: 'Flow' },
  { label: 'Unsubscribe', value: 'Unsubscribe' },
  { label: 'Subscribe again', value: 'Subscribe' },
]
const inputTypeOptions = ['Text', 'Email', 'Phone', 'Number'].map((value) => ({ label: value, value }))
const flowSelectOptions = computed(() => [
  { label: 'Select a flow', value: '' },
  ...flowOptions.value.map((item) => ({ label: item.label, value: item.name })),
])

function setFlag(target: Record<string, any>, key: string, value: unknown) {
  target[key] = value ? 1 : 0
}

function setTimeoutMinutes(value: string | number) {
  const text = String(value ?? '').trim()
  bot.value.session_timeout_minutes = text === '' || Number.isNaN(Number(text)) ? ('' as any) : Number(text)
}

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

function keywordResult(row: any) {
  if (row.response_type === 'Flow') return `Flow · ${displayTitle(row.trigger_flow) || 'Flow'}`
  if (row.response_type === 'Unsubscribe') return `Unsubscribe · ${row.response_text || ''}`
  if (row.response_type === 'Subscribe') return `Subscribe · ${row.response_text || ''}`
  return row.response_text || ''
}

function openKeyword(row?: any) {
  keywordForm.value = row
    ? {
        name: row.name,
        keywords: row.keywords || '',
        match_type: row.match_type || 'Contains',
        response_type: ['Flow', 'Unsubscribe', 'Subscribe'].includes(row.response_type) ? row.response_type : 'Text',
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

function removeKeyword(name: string) {
  dialog.danger({
    title: 'Delete keyword?',
    message: 'This keyword rule will be removed from the chatbot.',
    onConfirm: async () => {
      await deleteChatbotKeyword(account.value, name)
      keywords.value = keywords.value.filter((row) => row.name !== name)
    },
  })
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

function removeFlow(name: string) {
  dialog.danger({
    title: 'Delete flow?',
    message: 'This chatbot flow will be removed.',
    onConfirm: async () => {
      await deleteChatbotFlow(account.value, name)
      flows.value = flows.value.filter((row) => row.name !== name)
    },
  })
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
  syncAccount()
  if (!account.value) loading.value = false
}

watch(account, () => {
  if (account.value) loadAccount()
})

watch(accounts, () => {
  pickAccount()
})

watch(
  () => desk.account.value,
  () => {
    pickAccount()
  },
)

onMounted(async () => {
  await desk.load()
  pickAccount()
})
</script>

<template>
  <DeskPage variant="scroll">
    <template #tabs>
      <TabButtons v-model="tab" variant="underline" :options="tabOptions" />
    </template>

    <DeskEmpty v-if="!account" kind="account" :description="accountGateDescription" />
    <DeskEmpty v-else-if="loading" kind="loading" title="Loading automation…" />
    <DeskEmpty v-else-if="error" kind="error" :message="error" allow-retry @retry="loadAccount" />

    <div v-else-if="tab === 'bot'" class="space-y-4">
      <div class="grid items-start gap-4 lg:grid-cols-2">
        <DeskCard title="Set up the bot" description="Turn it on and save the reply used when no keyword or flow matches.">
          <template #actions>
            <Switch
              :model-value="Boolean(bot.enabled)"
              :label="bot.enabled ? 'Bot on' : 'Bot off'"
              @update:model-value="setFlag(bot, 'enabled', $event)"
            />
          </template>
          <div class="space-y-3">
            <FormControl
              v-model="bot.default_response"
              type="textarea"
              label="Default reply"
              :rows="4"
              placeholder="Thanks, we will reply shortly."
            />
            <FormControl
              :model-value="bot.session_timeout_minutes"
              type="number"
              min="5"
              label="Forget a chat after (minutes)"
              class="max-w-[12rem]"
              @update:model-value="setTimeoutMinutes"
            />
          </div>
        </DeskCard>

        <DeskCard title="Business hours" description="Outside these hours the bot sends the away message.">
          <template #actions>
            <Switch
              :model-value="Boolean(bot.business_hours_only)"
              label="Limit"
              @update:model-value="setFlag(bot, 'business_hours_only', $event)"
            />
          </template>
          <FormControl
            v-model="bot.out_of_hours_message"
            type="textarea"
            label="Away message"
            :rows="2"
            placeholder="We are closed. We will reply in the morning."
          />
          <div class="mt-3 divide-y divide-outline-gray-1 overflow-hidden rounded-lg border border-outline-gray-2">
            <div class="hidden grid-cols-[7.5rem_4.5rem_minmax(0,1fr)_minmax(0,1fr)] gap-2 bg-surface-gray-1 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-5 sm:grid">
              <span>Day</span>
              <span>Open</span>
              <span>From</span>
              <span>To</span>
            </div>
            <div v-for="row in bot.business_hours" :key="row.day" class="grid grid-cols-1 gap-2 px-3 py-2 sm:grid-cols-[7.5rem_4.5rem_minmax(0,1fr)_minmax(0,1fr)] sm:items-center">
              <span class="text-xs font-semibold text-ink-gray-8">{{ row.day }}</span>
              <Checkbox
                :model-value="Boolean(row.enabled)"
                label="Open"
                @update:model-value="setFlag(row, 'enabled', $event)"
              />
              <div>
                <span class="text-[11px] font-medium text-ink-gray-5 sm:sr-only">From</span>
                <TimePicker v-model="row.start_time" :disabled="!row.enabled" :interval="30" placeholder="From" />
              </div>
              <div>
                <span class="text-[11px] font-medium text-ink-gray-5 sm:sr-only">To</span>
                <TimePicker v-model="row.end_time" :disabled="!row.enabled" :interval="30" placeholder="To" />
              </div>
            </div>
          </div>
        </DeskCard>
      </div>

      <DeskCard title="AI fallback" description="Optional. The bot asks the model only after keywords and flows miss.">
        <template #actions>
          <Switch
            :model-value="Boolean(bot.enable_ai)"
            label="On"
            @update:model-value="setFlag(bot, 'enable_ai', $event)"
          />
        </template>
        <div v-if="bot.enable_ai" class="grid gap-3 sm:grid-cols-3">
          <FormControl
            v-model="bot.ai_provider"
            type="select"
            label="Provider"
            :options="providerOptions"
          />
          <FormControl v-model="bot.ai_model" type="text" label="Model" placeholder="gpt-4o-mini" />
          <FormControl
            v-model="bot.ai_api_key"
            type="password"
            label="API key"
            :placeholder="bot.has_ai_key ? 'Saved. Type a new key to replace it.' : 'Paste the key'"
          />
        </div>
        <FormControl
          v-model="bot.excluded_numbers"
          type="textarea"
          label="Never reply to"
          class="mt-4"
          :rows="2"
          placeholder="One phone number per line"
        />
        <div class="mt-4 flex justify-end">
          <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Save bot" :loading="saving" @click="saveBot" />
        </div>
      </DeskCard>
    </div>

    <div v-else-if="tab === 'keywords'">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p class="text-xs text-ink-gray-5">A matching word sends a reply or starts a flow.</p>
        <Button variant="solid" size="sm" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Add keyword" @click="openKeyword()" />
      </div>
      <DeskCard as="div" :padding="false" class="overflow-x-auto">
        <EmptyState v-if="!keywords.length" compact title="No keywords yet" description="A matching word sends a reply or starts a flow." />
        <table v-else class="w-full text-left text-sm">
          <thead class="border-b border-outline-gray-2 bg-surface-gray-1 text-xs font-semibold text-ink-gray-5">
            <tr>
              <th class="px-4 py-2.5 font-semibold">Words</th>
              <th class="px-4 py-2.5 font-semibold">Match</th>
              <th class="px-4 py-2.5 font-semibold">Reply</th>
              <th class="w-40 px-4 py-2.5" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in keywords" :key="row.name" class="border-b border-outline-gray-1 last:border-b-0">
              <td class="px-4 py-3 font-medium text-ink-gray-9">{{ row.keywords }}</td>
              <td class="px-4 py-3 text-ink-gray-6">{{ row.match_type }}</td>
              <td class="max-w-xs truncate px-4 py-3 text-ink-gray-7">{{ keywordResult(row) }}</td>
              <td class="px-4 py-3">
                <div class="flex justify-end gap-1">
                  <Button variant="ghost" size="sm" label="Edit" @click="openKeyword(row)" />
                  <Button variant="ghost" size="sm" theme="red" label="Delete" @click="removeKeyword(row.name)" />
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </DeskCard>
    </div>

    <div v-else-if="tab === 'flows'">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p class="text-xs text-ink-gray-5">Ask a few questions, then send the closing message. Use {email} to repeat a saved answer.</p>
        <Button variant="solid" size="sm" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Add flow" @click="openFlow()" />
      </div>
      <EmptyState v-if="!flows.length" title="No flows yet" description="Ask a few questions, then send a closing message." />
      <div v-else class="grid gap-3 lg:grid-cols-2">
        <DeskCard
          v-for="row in flows"
          :key="row.name"
          as="article"
          :title="displayTitle(row.flow_name) || 'Flow'"
          :description="`Starts on: ${row.trigger_keywords || 'a keyword that points here'}`"
        >
          <template #actions>
            <StatusBadge :label="row.enabled ? 'On' : 'Off'" />
          </template>
          <ol class="space-y-1 text-xs text-ink-gray-7">
            <li v-for="(step, index) in row.steps" :key="step.step_name">{{ Number(index) + 1 }}. {{ step.message }}</li>
          </ol>
          <div class="mt-3 flex justify-end gap-2">
            <Button variant="ghost" size="sm" label="Edit" @click="openFlow(row)" />
            <Button variant="ghost" size="sm" theme="red" label="Delete" @click="removeFlow(row.name)" />
          </div>
        </DeskCard>
      </div>
    </div>

    <div v-else class="grid items-start gap-4 lg:grid-cols-2">
      <DeskCard title="With an agent" description="The bot stays quiet until you hand the chat back.">
        <EmptyState v-if="!transfers.length" compact title="No handoffs" description="The bot stays quiet while an agent has the chat." />
        <ul v-else>
          <li v-for="row in transfers" :key="row.name" class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-1 py-3 last:border-b-0">
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-ink-gray-9">{{ row.phone_number }}</p>
              <p class="text-xs text-ink-gray-5">{{ row.agent_name || 'Unassigned' }} · {{ row.status }} · {{ when(row.transferred_at) }}</p>
            </div>
            <Button v-if="row.status === 'Active'" variant="subtle" size="sm" label="Resume bot" @click="resume(row.name)" />
          </li>
        </ul>
      </DeskCard>
      <DeskCard title="In a flow" description="Someone is answering questions. Stop it to let the normal bot reply.">
        <EmptyState v-if="!sessions.length" compact title="No active flows" description="Stop a flow to let the normal bot reply." />
        <ul v-else>
          <li v-for="row in sessions" :key="row.name" class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-1 py-3 last:border-b-0">
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-ink-gray-9">{{ row.phone_number }}</p>
              <p class="text-xs text-ink-gray-5">{{ displayTitle(row.current_flow) || 'Flow' }} · {{ displayTitle(row.current_step) || 'Step' }}</p>
            </div>
            <Button variant="subtle" size="sm" label="Stop" @click="cancelSession(row.name)" />
          </li>
        </ul>
      </DeskCard>
    </div>

    <Dialog v-model="keywordOpen" :title="keywordForm.name ? 'Edit keyword' : 'Add keyword'">
      <div class="space-y-3">
        <FormControl
          v-model="keywordForm.keywords"
          type="text"
          label="Words, separated by commas"
          placeholder="hello, hi"
        />
        <div class="grid gap-3 sm:grid-cols-2">
          <FormControl
            v-model="keywordForm.match_type"
            type="select"
            label="Match"
            :options="matchTypeOptions"
          />
          <FormControl
            v-model="keywordForm.response_type"
            type="select"
            label="Then"
            :options="responseTypeOptions"
          />
        </div>
        <FormControl
          v-if="keywordForm.response_type !== 'Flow'"
          v-model="keywordForm.response_text"
          type="textarea"
          label="Reply"
          :rows="3"
        />
        <FormControl
          v-else
          v-model="keywordForm.trigger_flow"
          type="select"
          label="Flow"
          :options="flowSelectOptions"
        />
        <Checkbox
          :model-value="Boolean(keywordForm.enabled)"
          label="Enabled"
          @update:model-value="setFlag(keywordForm, 'enabled', $event)"
        />
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
          <FormControl
            v-model="flowForm.flow_name"
            type="text"
            label="Name"
            placeholder="Book a demo"
            :disabled="Boolean(flowForm.name)"
          />
          <FormControl
            v-model="flowForm.trigger_keywords"
            type="text"
            label="Start words"
            placeholder="book, demo"
          />
        </div>
        <FormControl
          v-model="flowForm.initial_message"
          type="text"
          label="Opening message"
          placeholder="Sure, a few quick questions."
        />
        <div class="space-y-2">
          <div v-for="(step, index) in flowForm.steps" :key="index" class="rounded-lg border border-outline-gray-2 p-3">
            <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_8rem_auto] sm:items-end">
              <FormControl v-model="step.message" type="text" label="Question" placeholder="What is your email?" />
              <FormControl v-model="step.input_type" type="select" label="Answer" :options="inputTypeOptions" />
              <FormControl v-model="step.store_as" type="text" label="Save as" placeholder="email" />
              <Button variant="ghost" theme="red" label="Remove" @click="removeStep(index)" />
            </div>
          </div>
        </div>
        <Button variant="subtle" size="sm" label="Add question" @click="addStep" />
        <div class="grid gap-3 sm:grid-cols-2">
          <FormControl
            v-model="flowForm.completion_message"
            type="text"
            label="Closing message"
            placeholder="Booked for {email}"
          />
          <FormControl
            v-model="flowForm.cancel_keywords"
            type="text"
            label="Cancel words"
            placeholder="stop, cancel"
          />
        </div>
        <Checkbox
          :model-value="Boolean(flowForm.enabled)"
          label="Enabled"
          @update:model-value="setFlag(flowForm, 'enabled', $event)"
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="flowOpen = false" />
          <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Save" :loading="saving" @click="saveFlow" />
        </div>
      </template>
    </Dialog>
  </DeskPage>
</template>
