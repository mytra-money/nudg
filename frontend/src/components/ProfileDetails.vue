<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Avatar, Badge, Button, Combobox, Dialog, Dropdown, Tooltip } from 'frappe-ui'
import { isManager } from '@/desk'
import { deskRoute, whatsappScreen } from '@/format'
import { listAssignableUsers } from '@/phase2'
import { router } from '@/router'
import type { AssignmentInfo, Thread } from '@/types'

const props = defineProps<{
  thread: Thread
  assignment?: AssignmentInfo | null
}>()

const emit = defineEmits<{
  assign: [user: string]
  unassign: []
}>()

function linkedScreen(doctype: string) {
  const screen = whatsappScreen(doctype)
  if (!screen || (screen.manager && !isManager.value)) return null
  return screen
}

function canOpen(doctype: string) {
  if (isManager.value) return true
  return Boolean(linkedScreen(doctype))
}

function openLinked(doctype: string, name: string) {
  if (isManager.value) {
    window.location.href = deskRoute(doctype, name)
    return
  }
  const screen = linkedScreen(doctype)
  if (!screen) return
  void router.push(screen.path)
}

const assignDialogOpen = ref(false)
const newAssignee = ref<string | null>(null)
const userQuery = ref('')
const userOptions = ref<Array<{ value: string; label: string; description?: string }>>([])
const usersLoading = ref(false)
let userSearchTimer = 0

async function loadUsers(txt = '') {
  usersLoading.value = true
  try {
    const rows = await listAssignableUsers(txt)
    userOptions.value = Array.isArray(rows) ? rows : []
  } catch {
    userOptions.value = []
  } finally {
    usersLoading.value = false
  }
}

watch(assignDialogOpen, (open) => {
  if (!open) return
  newAssignee.value = null
  userQuery.value = ''
  void loadUsers('')
})

watch(userQuery, (query) => {
  const selected = userOptions.value.find((row) => row.value === newAssignee.value)
  if (selected && query === selected.label) return
  window.clearTimeout(userSearchTimer)
  userSearchTimer = window.setTimeout(() => void loadUsers(query), 200)
})

const links = computed(() => {
  const seen = new Set(props.thread.references.map((link) => `${link.doctype}:${link.docname}`))
  return [
    ...props.thread.references,
    ...props.thread.links.filter((link) => !seen.has(`${link.doctype}:${link.docname}`)),
  ]
})

const profileInitials = computed(() => {
  const name = props.thread.profile.profile_name || props.thread.profile.phone_number || '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
})

const assigneeInitials = computed(() => {
  if (!props.assignment?.assignee) return ''
  const parts = props.assignment.assignee.split('@')[0].split(/[._-]/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
})

function submitAssignment() {
  const user = newAssignee.value?.trim()
  if (!user) return
  emit('assign', user)
  newAssignee.value = null
  assignDialogOpen.value = false
}

function handleUnassign() {
  emit('unassign')
}
</script>

<template>
  <div class="flex h-full flex-col overflow-y-auto divide-y divide-outline-gray-2 text-sm text-ink-gray-8">
    <!-- Contact Card / Avatar Header -->
    <div class="flex flex-col items-center p-4 text-center">
      <div class="relative inline-flex">
        <Avatar
          :label="thread.profile.profile_name || thread.profile.phone_number"
          size="3xl"
        />
        <span
          class="absolute bottom-0 right-0 size-3 rounded-full border-2 border-white"
          :class="thread.profile.status === 'Active' ? 'bg-[#25D366]' : 'bg-gray-400'"
          :title="thread.profile.status"
        />
      </div>

      <h2 class="mt-2.5 font-semibold text-sm text-ink-gray-9 tracking-tight">
        {{ thread.profile.profile_name || thread.profile.phone_number }}
      </h2>
      <p class="text-xs text-ink-gray-5 font-mono mt-0.5">
        {{ thread.profile.phone_number }}
      </p>

      <div class="mt-2 flex items-center gap-1.5 flex-wrap justify-center">
        <Badge
          :theme="thread.profile.status === 'Active' ? 'green' : 'gray'"
          variant="subtle"
          size="sm"
          :label="thread.profile.status"
        />
        <Badge
          theme="blue"
          variant="subtle"
          size="sm"
          :label="thread.profile.whatsapp_account"
        />
      </div>
    </div>

    <!-- Assigned To (Frappe Form Sidebar Native Replica) -->
    <div class="p-4 space-y-2.5">
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wider text-ink-gray-5 flex items-center gap-1.5">
          <span class="lucide-users size-3.5" aria-hidden="true" />
          Assigned To
        </span>
        <Button
          variant="ghost"
          size="sm"
          icon="lucide-plus"
          label="Assign"
          @click="assignDialogOpen = true"
        />
      </div>

      <!-- Current Assignee Card -->
      <div
        v-if="assignment?.assignee"
        class="flex items-center justify-between rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-xs"
      >
        <div class="flex items-center gap-2.5 min-w-0">
          <Avatar
            :label="assignment.assignee"
            size="sm"
          />
          <div class="min-w-0">
            <p class="truncate font-medium text-ink-gray-9 leading-tight">
              {{ assignment.assignee }}
            </p>
            <p class="text-[11px] text-ink-gray-5">
              {{ assignment.assignment_status }}
            </p>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          icon="lucide-x"
          title="Remove assignment"
          @click="handleUnassign"
        />
      </div>

      <div
        v-else
        class="rounded-lg border border-dashed border-outline-gray-2 p-3 text-center text-xs text-ink-gray-5"
      >
        <span>No agent assigned yet.</span>
      </div>
    </div>

    <!-- Linked Documents Section -->
    <div class="p-4 space-y-2.5">
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold uppercase tracking-wider text-ink-gray-5 flex items-center gap-1.5">
          <span class="lucide-link-2 size-3.5" aria-hidden="true" />
          Linked Documents
        </span>
        <span v-if="links.length" class="text-xs text-ink-gray-5 font-mono">
          ({{ links.length }})
        </span>
      </div>

      <div v-if="links.length" class="space-y-1.5">
        <component
          :is="canOpen(link.doctype) ? 'button' : 'div'"
          v-for="link in links"
          :key="link.doctype + link.docname"
          :type="canOpen(link.doctype) ? 'button' : undefined"
          class="flex w-full items-center justify-between rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-left text-xs"
          :class="canOpen(link.doctype) ? 'transition-colors hover:border-[#128C7E] hover:bg-surface-gray-1 group' : ''"
          @click="canOpen(link.doctype) && openLinked(link.doctype, link.docname)"
        >
          <div class="min-w-0">
            <span class="font-medium text-ink-gray-9" :class="canOpen(link.doctype) ? 'group-hover:text-[#075E54]' : ''">
              {{ link.title || link.docname }}
            </span>
            <span class="block text-[11px] text-ink-gray-5 mt-0.5">
              {{ link.doctype }}
            </span>
          </div>
        </component>
      </div>

      <div
        v-else
        class="rounded-lg border border-dashed border-outline-gray-2 p-3 text-center text-xs text-ink-gray-5"
      >
        <span>No Frappe records linked yet. Send templates to auto-link.</span>
      </div>
    </div>

    <!-- Quick Meta Information Footer -->
    <div class="p-4 bg-surface-gray-1 text-xs text-ink-gray-5 space-y-1">
      <div class="flex items-baseline justify-between gap-2">
        <span class="shrink-0">Account ID:</span>
        <span class="min-w-0 truncate text-right font-mono text-ink-gray-7">{{ thread.profile.whatsapp_account }}</span>
      </div>
      <div class="flex items-baseline justify-between gap-2">
        <span class="shrink-0">Window:</span>
        <span class="font-medium" :class="thread.window.status === 'open' ? 'text-[#25D366]' : 'text-ink-gray-6'">
          {{ thread.window.status === 'open' ? '24h Window Open' : 'Template Only' }}
        </span>
      </div>
    </div>

    <!-- Dialog for Assigning User -->
    <Dialog v-model="assignDialogOpen" title="Assign Conversation" size="md">
      <div class="space-y-4 py-2">
        <p class="text-xs text-ink-gray-6">
          Select the team member to assign this conversation to.
        </p>
        <Combobox
          v-model="newAssignee"
          v-model:query="userQuery"
          :options="userOptions"
          :loading="usersLoading"
          :filterable="false"
          open-on-focus
          placeholder="Select a user"
          empty-text="No users found"
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="assignDialogOpen = false" />
          <Button variant="solid" theme="green" label="Assign" :disabled="!newAssignee" @click="submitAssignment" />
        </div>
      </template>
    </Dialog>
  </div>
</template>
