<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Badge, Button, Checkbox, Dialog, FormControl, Switch, TabButtons, TimePicker, dialog, toast } from 'frappe-ui'
import DeskCard from '@/components/desk/DeskCard.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import EmptyState from '@/components/EmptyState.vue'
import MetaFlowsPanel from '@/components/MetaFlowsPanel.vue'
import { formatDay, formatTime, rawErrorText } from '@/utils/format'
import { displayTitle } from '@/utils/titles'
import {
  cancelChatbotSession,
  deleteChatbotKeyword,
  getChatbot,
  listChatbotHandoffs,
  listChatbotKeywords,
  resumeChatbotHandoff,
  saveChatbot,
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

const tab = ref<Tab>('bot')
const account = ref('')
const { desk, accounts, accountGateDescription, selectedAccountLabel, syncAccount } = useAccountGate({ account })
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
const transfers = ref<any[]>([])
const sessions = ref<any[]>([])

const keywordOpen = ref(false)
const keywordForm = ref(emptyKeyword())

const tabOptions: { value: Tab; label: string }[] = [
  { value: 'bot', label: 'Set up bot' },
  { value: 'keywords', label: 'Keywords' },
  { value: 'flows', label: 'Meta Flows' },
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
  { label: 'Unsubscribe', value: 'Unsubscribe' },
  { label: 'Subscribe again', value: 'Subscribe' },
]

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
    enabled: 1,
  }
}

function clock(value: string) {
  return (value || '').slice(0, 5)
}

async function loadAccount() {
  if (!account.value) return
  loading.value = true
  error.value = null
  try {
    const [settings, keywordRows, handoff] = await Promise.all([
      getChatbot(account.value),
      listChatbotKeywords(account.value),
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
        response_type: ['Unsubscribe', 'Subscribe'].includes(row.response_type) ? row.response_type : 'Text',
        response_text: row.response_text || '',
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
            :placeholder="bot.has_ai_key ? 'Leave blank to keep the current key' : 'Paste the key'"
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
          <Button variant="solid" theme="green" loading-text="Saving…" label="Save bot" :loading="saving" @click="saveBot"/>
        </div>
      </DeskCard>
    </div>

    <div v-else-if="tab === 'keywords'">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p class="text-xs text-ink-gray-5">A matching word sends a reply or starts a flow.</p>
        <Button variant="solid" theme="green" size="sm" label="Add keyword" @click="openKeyword()"/>
      </div>
      <DeskCard as="div" :padding="false" class="overflow-hidden">
        <EmptyState v-if="!keywords.length" compact title="No keywords yet" description="A matching word sends a reply or starts a flow." />
        <div v-else class="divide-y divide-outline-gray-1">
          <ItemListRow
            v-for="row in keywords"
            :key="row.name"
            as="div"
            size="lg"
            class="px-4 py-3 hover:bg-surface-gray-1"
          >
            <template #label>
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-ink-gray-9">{{ row.keywords }}</p>
                <p class="truncate text-xs text-ink-gray-6">{{ keywordResult(row) }}</p>
              </div>
            </template>
            <template #suffix>
              <div class="flex items-center gap-2">
                <Badge :label="row.match_type" variant="subtle" theme="gray" size="sm" />
                <Button variant="ghost" size="sm" label="Edit" @click="openKeyword(row)" />
                <Button variant="ghost" size="sm" theme="red" label="Delete" @click="removeKeyword(row.name)" />
              </div>
            </template>
          </ItemListRow>
        </div>
      </DeskCard>
    </div>

    <div v-else-if="tab === 'flows'" class="flex min-h-[28rem] flex-col">
      <MetaFlowsPanel :key="account" :account="account" />
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
        <p class="text-xs text-ink-gray-5">
          WhatsApp account: {{ displayTitle(selectedAccountLabel) || 'Select a number in the top bar' }}
        </p>
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
          v-model="keywordForm.response_text"
          type="textarea"
          label="Reply"
          :rows="3"
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
          <Button variant="solid" theme="green" loading-text="Saving…" label="Save" :loading="saving" @click="saveKeyword"/>
        </div>
      </template>
    </Dialog>
  </DeskPage>
</template>
