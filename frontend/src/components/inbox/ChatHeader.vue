<script setup lang="ts">
import { Avatar, Button, Dropdown } from 'frappe-ui'
import { formatRemaining } from '@/utils/format'
import type { Profile, WindowState } from '@/types'

defineProps<{
  profile: Profile
  windowState: WindowState | null
  now: number
  mode: 'live' | 'sample'
  headerAssignees: string[]
  notesCount: number
  notesOpen: boolean
  chatSearchOpen: boolean
  assigneeSummary: (users: string[]) => string
  agentLabel: (user: string) => string
}>()

const emit = defineEmits<{
  back: []
  openContact: []
  openAssign: []
  assignToMe: []
  clearAssignment: []
  toggleNotes: []
  toggleSearch: []
  simulateReply: []
}>()
</script>

<template>
  <header class="inbox-chat-header sticky top-0 z-10 flex h-14 shrink-0 items-center gap-1 overflow-hidden border-b border-wa bg-white px-2 sm:gap-2 sm:px-3">
    <div class="inbox-contact flex min-w-0 flex-1 items-center gap-2">
      <button
        type="button"
        class="inline-flex size-9 items-center justify-center rounded-full text-wa-muted hover:bg-wa-panel md:hidden"
        title="Back to conversation list"
        @click="emit('back')"
      >
        <span class="lucide-arrow-left size-5" aria-hidden="true" />
      </button>

      <button
        type="button"
        class="flex min-w-0 items-center gap-2.5 rounded-lg text-left hover:bg-wa-panel"
        title="Contact info"
        @click="emit('openContact')"
      >
        <span class="relative shrink-0">
          <Avatar :label="profile.profile_name || profile.phone_number" size="lg" />
          <span
            v-if="profile.status === 'Active'"
            class="absolute bottom-0 right-0 size-2.5 rounded-full bg-wa-accent ring-2 ring-white"
          />
        </span>
        <span class="min-w-0">
          <span class="block truncate text-sm font-semibold leading-tight text-wa-ink">
            {{ profile.profile_name || profile.phone_number }}
          </span>
          <span class="block truncate text-xs leading-tight text-wa-subtle">
            {{ profile.phone_number }}
          </span>
        </span>
      </button>
    </div>

    <div class="flex shrink-0 items-center gap-1.5">
      <div
        v-if="windowState?.status === 'open'"
        class="hidden items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 sm:inline-flex"
        title="24-hour customer care window is open"
      >
        <span class="size-1.5 rounded-full bg-emerald-500" />
        <span>{{ formatRemaining(windowState.expires_at, now) }}</span>
      </div>
      <div
        v-else
        class="hidden items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 sm:inline-flex"
        title="24-hour window is closed. Send an approved template."
      >
        Window closed
      </div>

      <Button
        v-if="mode === 'sample' && windowState?.status === 'closed'"
        size="sm"
        variant="subtle"
        label="Simulate reply"
        @click="emit('simulateReply')"
      />

      <Dropdown
        :options="[
          { label: 'Assign to me', onClick: () => emit('assignToMe') },
          { label: 'Assign', onClick: () => emit('openAssign') },
          ...(headerAssignees.length
            ? [{ label: 'Unassign all', onClick: () => emit('clearAssignment') }]
            : []),
        ]"
      >
        <button
          type="button"
          class="hidden h-8 items-center gap-1.5 rounded-full border border-wa bg-white px-2 text-xs font-medium text-wa-ink hover:bg-wa-panel sm:inline-flex"
        >
          <span v-if="headerAssignees.length" class="flex items-center">
            <Avatar
              v-for="person in headerAssignees.slice(0, 3)"
              :key="person"
              :label="agentLabel(person)"
              size="sm"
              class="-ml-1 first:ml-0"
            />
          </span>
          <Avatar v-else label="Unassigned" size="sm" />
          <span class="whitespace-nowrap">{{ assigneeSummary(headerAssignees) }}</span>
          <span class="lucide-chevron-down size-3 text-wa-subtle" aria-hidden="true" />
        </button>
      </Dropdown>

      <button
        type="button"
        class="inline-flex size-8 shrink-0 items-center justify-center rounded-full text-wa-muted hover:bg-wa-panel sm:hidden"
        title="Assign"
        @click="emit('openAssign')"
      >
        <span class="lucide-user-plus size-4" aria-hidden="true" />
      </button>

      <button
        type="button"
        class="inline-flex h-8 shrink-0 items-center gap-1 rounded-full px-2 text-xs font-medium text-wa-muted hover:bg-wa-panel"
        :class="notesOpen ? 'bg-emerald-50 text-emerald-700' : ''"
        :title="notesCount ? `Notes ${notesCount}` : 'Notes'"
        @click="emit('toggleNotes')"
      >
        <span class="lucide-sticky-note size-4" aria-hidden="true" />
        <span class="hidden sm:inline">Notes<span v-if="notesCount"> {{ notesCount }}</span></span>
        <span v-if="notesCount" class="sm:hidden text-[11px] font-semibold">{{ notesCount }}</span>
      </button>

      <button
        type="button"
        class="grid size-8 place-items-center rounded-full text-ink-gray-6 hover:bg-surface-gray-2"
        :class="chatSearchOpen ? 'bg-surface-gray-2 text-ink-gray-9' : ''"
        title="Search in conversation"
        @click="emit('toggleSearch')"
      >
        <span class="lucide-search size-4" aria-hidden="true" />
      </button>
    </div>
  </header>
</template>
