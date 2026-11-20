<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, toast } from 'frappe-ui'
import { resumeChatbotHandoff } from '@/services/catalogApi'
import { errorText } from '@/utils/format'
import type { BotStatus } from '@/types'

const props = defineProps<{
  botStatus?: BotStatus | null
  account?: string | null
}>()

const emit = defineEmits<{
  resumed: []
}>()

const busy = ref(false)

const visible = computed(() => {
  const status = props.botStatus
  if (!status?.installed) return false
  return Boolean(status.is_transferred || status.has_bot_session)
})

const title = computed(() => {
  if (props.botStatus?.is_transferred) return 'Bot paused — handed to an agent'
  if (props.botStatus?.has_bot_session) return 'Chatbot session active'
  return ''
})

const detail = computed(() => {
  const status = props.botStatus
  if (!status) return ''
  if (status.is_transferred) {
    const agent = status.transfer?.agent_name || status.transfer?.agent || 'an agent'
    return `Waiting on ${agent}. Return to bot when the human conversation is done.`
  }
  if (status.flow_title) return `Flow: ${status.flow_title}`
  return 'The customer is in an automated flow.'
})

async function resumeBot() {
  const transferName = props.botStatus?.transfer?.name
  const account = props.account
  if (!transferName || !account) {
    toast.error('This handoff cannot be resumed from here.')
    return
  }
  busy.value = true
  try {
    await resumeChatbotHandoff(account, transferName)
    toast.success('Chatbot resumed')
    emit('resumed')
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    v-if="visible"
    class="flex flex-col gap-2 border-b px-4 py-2.5 text-xs sm:flex-row sm:items-center sm:justify-between"
    :class="
      botStatus?.is_transferred
        ? 'border-sky-200 bg-sky-50 text-sky-950'
        : 'border-violet-200 bg-violet-50 text-violet-950'
    "
  >
    <div class="flex min-w-0 items-start gap-2">
      <span
        class="mt-0.5 size-4 shrink-0"
        :class="botStatus?.is_transferred ? 'lucide-user-round' : 'lucide-bot'"
        aria-hidden="true"
      />
      <div class="min-w-0">
        <p class="font-semibold">{{ title }}</p>
        <p class="mt-0.5 text-[11px] opacity-90">{{ detail }}</p>
      </div>
    </div>
    <Button
      v-if="botStatus?.is_transferred && botStatus.transfer?.name && account"
      size="sm"
      variant="solid"
      class="w-full shrink-0 sm:w-auto"
      label="Return to bot"
      :loading="busy"
      @click="resumeBot"
    />
  </div>
</template>
