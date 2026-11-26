<script setup lang="ts">
import { computed, reactive } from 'vue'
import { Avatar, Badge, Button } from 'frappe-ui'
import { formatTime, previewText } from '@/utils/format'
import type { Conversation } from '@/types'

const props = defineProps<{
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

const expanded = reactive<{ chats: boolean; contacts: boolean }>({
  chats: true,
  contacts: true,
})

function hasInitiatedChat(row: Conversation): boolean {
  return row.has_messages ?? Boolean(row.preview)
}

const sections = computed(() => {
  const chats: Conversation[] = []
  const contacts: Conversation[] = []
  for (const row of props.conversations) {
    if (hasInitiatedChat(row)) chats.push(row)
    else contacts.push(row)
  }
  return [
    {
      key: 'chats' as const,
      label: 'Chats',
      emptyText: 'No active chats yet.',
      items: chats,
    },
    {
      key: 'contacts' as const,
      label: 'Contacts',
      emptyText: 'No contacts without messages.',
      items: contacts,
    },
  ]
})

function toggleSection(key: 'chats' | 'contacts') {
  expanded[key] = !expanded[key]
}
</script>

<template>
  <div class="min-h-0 flex-1 overflow-y-auto">
    <div v-if="conversations.length === 0" class="p-6 text-center text-xs text-ink-gray-5">
      <div class="mx-auto grid size-10 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-4">
        <span class="lucide-search-x size-5" aria-hidden="true" />
      </div>
      <p class="mt-2 font-medium text-ink-gray-8">No conversations found</p>
      <p class="mt-1 text-ink-gray-5">No threads match this search or these filters.</p>
      <Button
        variant="ghost"
        size="sm"
        label="Clear all filters"
        class="mt-3 text-wa-teal"
        @click="emit('clearFilters')"
      />
    </div>

    <div v-else class="divide-y divide-outline-gray-1">
      <section v-for="section in sections" :key="section.key">
        <button
          type="button"
          class="sticky top-0 z-[1] flex w-full items-center justify-between bg-surface-gray-1 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-ink-gray-6 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-wa-mid"
          :aria-expanded="expanded[section.key]"
          @click="toggleSection(section.key)"
        >
          <span class="flex items-center gap-1.5">
            <span
              class="size-3.5 transition-transform"
              :class="expanded[section.key] ? 'lucide-chevron-down' : 'lucide-chevron-right'"
              aria-hidden="true"
            />
            <span>{{ section.label }}</span>
          </span>
          <Badge :label="String(section.items.length)" variant="subtle" theme="gray" size="sm" />
        </button>

        <div v-if="expanded[section.key]" class="divide-y divide-outline-gray-1">
          <p
            v-if="section.items.length === 0"
            class="px-3 py-3 text-xs text-ink-gray-5"
          >
            {{ section.emptyText }}
          </p>

          <button
            v-for="row in section.items"
            :key="row.profile.name"
            type="button"
            class="flex w-full gap-3 px-3 py-3 text-left transition-all hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-wa-mid"
            :class="
              selected === row.profile.name
                ? 'bg-surface-gray-2 border-l-4 border-l-ink-gray-9'
                : 'border-l-4 border-l-transparent'
            "
            @click="emit('select', row)"
          >
            <div class="shrink-0 self-start">
              <Avatar :label="row.profile.profile_name || row.profile.phone_number" size="xl">
                <template #indicator>
                  <span
                    v-if="rowStatus(row) === 'window_open'"
                    class="size-2.5 rounded-full bg-green-500 ring-2 ring-white"
                    title="24h service window open"
                  />
                  <span
                    v-else-if="row.needs_reply"
                    class="size-2.5 rounded-full bg-red-500 ring-2 ring-white"
                    title="Needs reply"
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
                    selected === row.profile.name ? 'text-ink-gray-9' : 'text-ink-gray-8',
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
                  <template v-if="hasInitiatedChat(row)">
                    <span v-if="row.preview?.direction === 'Outgoing'" class="font-medium text-ink-gray-5">You: </span>
                    <span>{{ previewText(row.preview) }}</span>
                  </template>
                  <template v-else>
                    <span>{{ row.profile.phone_number }}</span>
                  </template>
                </p>
              </div>

              <div class="flex shrink-0 flex-col items-end gap-1">
                <span
                  class="text-[11px] font-mono"
                  :class="unreadCount(row) ? 'font-semibold text-green-600' : 'text-ink-gray-5'"
                >
                  {{ row.preview?.creation ? formatTime(row.preview.creation) : '' }}
                </span>
                <span
                  v-if="unreadCount(row) > 0"
                  class="grid h-5 min-w-5 place-items-center rounded-full bg-wa-accent px-1.5 text-[11px] font-semibold leading-none text-white"
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
        </div>
      </section>

      <Button
        v-if="hasMore"
        variant="ghost"
        size="sm"
        label="Load more conversations"
        class="w-full rounded-none py-3 text-wa-teal"
        @click="emit('loadMore')"
      />
    </div>
  </div>
</template>
