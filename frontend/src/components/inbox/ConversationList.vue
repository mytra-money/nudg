<script setup lang="ts">
import { Avatar } from 'frappe-ui'
import { formatTime, previewText } from '@/utils/format'
import type { Conversation } from '@/types'

defineProps<{
  conversations: Conversation[]
  selected?: string | null
  hasMore?: boolean
  rowStatus: (row: Conversation) => string
  unreadCount: (row: Conversation) => number
  assigneesOf: (row: Conversation) => string[]
  agentLabel: (user: string) => string
}>()

const emit = defineEmits<{
  select: [row: Conversation]
  clearFilters: []
  loadMore: []
}>()
</script>

<template>
  <div class="min-h-0 flex-1 overflow-y-auto divide-y divide-outline-gray-1">
    <div v-if="conversations.length === 0" class="p-6 text-center text-xs text-ink-gray-5">
      <div class="mx-auto grid size-10 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-4">
        <span class="lucide-search-x size-5" aria-hidden="true" />
      </div>
      <p class="mt-2 font-medium text-ink-gray-8">No conversations found</p>
      <p class="mt-1 text-ink-gray-5">No threads match this search or these filters.</p>
      <button
        type="button"
        class="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-[#075E54] hover:underline"
        @click="emit('clearFilters')"
      >
        Clear all filters
      </button>
    </div>

    <button
      v-for="row in conversations"
      :key="row.profile.name"
      type="button"
      class="flex w-full gap-3 px-3 py-3 text-left transition-all hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#128C7E]"
      :class="
        selected === row.profile.name
          ? 'bg-teal-50/70 border-l-4 border-l-[#075E54]'
          : 'border-l-4 border-l-transparent'
      "
      @click="emit('select', row)"
    >
      <div class="shrink-0 self-start">
        <Avatar :label="row.profile.profile_name || row.profile.phone_number" size="xl">
          <template #indicator>
            <span
              v-if="rowStatus(row) === 'window_open'"
              class="size-2.5 rounded-full bg-[#25D366] ring-2 ring-white"
              title="24h Service Window Open"
            />
            <span
              v-else-if="row.needs_reply"
              class="size-2.5 rounded-full bg-red-500 ring-2 ring-white"
              title="Needs Reply"
            />
          </template>
        </Avatar>
      </div>

      <div class="flex min-w-0 flex-1 items-start justify-between gap-2">
        <div class="min-w-0 flex-1">
          <span
            class="flex items-center gap-1.5 truncate text-sm leading-snug"
            :class="[
              unreadCount(row) ? 'font-bold' : 'font-semibold',
              selected === row.profile.name ? 'text-[#075E54]' : 'text-ink-gray-9',
            ]"
          >
            <span class="truncate">{{ row.profile.profile_name || row.profile.phone_number }}</span>
            <span
              v-if="row.bot_status?.is_transferred"
              class="lucide-user-round size-3 shrink-0 text-sky-600"
              title="Handed to agent"
              aria-hidden="true"
            />
            <span
              v-else-if="row.bot_status?.has_bot_session"
              class="lucide-bot size-3 shrink-0 text-violet-600"
              title="In chatbot flow"
              aria-hidden="true"
            />
          </span>
          <p
            class="mt-0.5 truncate text-xs"
            :class="unreadCount(row) ? 'font-medium text-ink-gray-8' : 'text-ink-gray-6'"
          >
            <span v-if="row.preview?.direction === 'Outgoing'" class="font-medium text-ink-gray-5">You: </span>
            <span>{{ previewText(row.preview) }}</span>
          </p>
        </div>

        <div class="flex shrink-0 flex-col items-end gap-1">
          <span
            class="text-[11px] font-mono"
            :class="unreadCount(row) ? 'font-semibold text-[#25D366]' : 'text-ink-gray-5'"
          >
            {{ row.preview?.creation ? formatTime(row.preview.creation) : '' }}
          </span>
          <span
            v-if="unreadCount(row) > 0"
            class="grid h-5 min-w-5 place-items-center rounded-full bg-[#25D366] px-1.5 text-[11px] font-semibold leading-none text-white"
            :title="`${unreadCount(row)} unread`"
          >
            {{ unreadCount(row) > 99 ? '99+' : unreadCount(row) }}
          </span>
          <div v-if="assigneesOf(row).length" class="flex items-center justify-end">
            <Avatar
              v-for="person in assigneesOf(row).slice(0, 3)"
              :key="person"
              :label="agentLabel(person)"
              size="sm"
              theme="blue"
              class="-ml-1 first:ml-0"
              :title="agentLabel(person)"
            />
          </div>
        </div>
      </div>
    </button>

    <button
      v-if="hasMore"
      type="button"
      class="w-full px-3 py-3 text-center text-xs font-semibold text-[#075E54] hover:bg-surface-gray-1"
      @click="emit('loadMore')"
    >
      Load more conversations
    </button>
  </div>
</template>
