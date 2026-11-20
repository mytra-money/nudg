<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Avatar, Button, Combobox, Dialog, toast } from 'frappe-ui'
import { isManager } from '@/stores/desk'
import { whatsappScreen } from '@/utils/format'
import { listAssignableUsers } from '@/services/catalogApi'
import { userLabel } from '@/utils/frappeSession'
import { router } from '@/router'
import type { AssignmentInfo, Thread } from '@/types'

const props = defineProps<{
  thread: Thread
  assignment?: AssignmentInfo | null
}>()

const emit = defineEmits<{
  assign: [user: string]
  unassign: [user: string]
}>()

function linkedScreen(doctype: string) {
  const screen = whatsappScreen(doctype)
  if (!screen || (screen.manager && !isManager.value)) return null
  return screen
}

function canOpen(doctype: string) {
  return Boolean(linkedScreen(doctype))
}

function openLinked(doctype: string, name: string) {
  const screen = linkedScreen(doctype)
  if (!screen || !name) return
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

onMounted(() => {
  void loadUsers('')
})

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

function submitAssignment() {
  const user = newAssignee.value?.trim()
  if (!user) return
  emit('assign', user)
  newAssignee.value = null
  assignDialogOpen.value = false
}

const assignees = computed(() => {
  const listed = (props.assignment?.assignees || []).filter((person): person is string => Boolean(person))
  if (listed.length) return listed
  const one = props.assignment?.assignee
  if (!one || props.assignment?.assignment_status === 'Unassigned') return []
  return [one]
})

function personLabel(user: string) {
  const known = userOptions.value.find((row) => row.value === user)?.label
  if (known) return known
  return userLabel(user)
}

function handleUnassign(user: string) {
  emit('unassign', user)
}

function promptLink() {
  toast.success('Send a template tied to a document, such as a Lead or Sales Invoice, to link it here.')
}

function openAssign() {
  assignDialogOpen.value = true
}

defineExpose({ openAssign })
</script>

<template>
  <div class="flex flex-col text-[13px] text-[#111B21]">
    <div class="flex flex-col items-center px-3 py-3 text-center">
      <div class="relative inline-flex">
        <Avatar
          :label="thread.profile.profile_name || thread.profile.phone_number"
          size="2xl"
        />
        <span
          class="absolute bottom-0 right-0 size-3 rounded-full border-2 border-white"
          :class="thread.profile.status === 'Active' ? 'bg-[#25D366]' : 'bg-gray-400'"
          :title="thread.profile.status"
        />
      </div>
      <h2 class="mt-2 text-sm font-semibold leading-snug text-[#111B21]">
        {{ thread.profile.profile_name || thread.profile.phone_number }}
      </h2>
      <p class="mt-0.5 text-xs text-[#667781]">
        {{ thread.profile.phone_number }}
      </p>
      <span class="mt-2 inline-flex max-w-full items-center rounded-full bg-[#F0F2F5] px-2.5 py-0.5 text-[11px] font-medium text-[#54656F]">
        WhatsApp {{ thread.profile.whatsapp_account }}
      </span>
    </div>

    <div class="space-y-1.5 border-t border-[#E9EDEF] px-3 py-2">
      <div class="flex items-center justify-between gap-2">
        <span class="text-[11px] font-semibold uppercase tracking-wide text-[#667781]">Assigned to</span>
        <button
          type="button"
          class="text-[11px] font-semibold text-[#00A884] hover:underline"
          @click="assignDialogOpen = true"
        >
          Assign
        </button>
      </div>
      <div v-if="assignees.length" class="space-y-1">
        <div
          v-for="person in assignees"
          :key="person"
          class="flex items-center gap-2 rounded-lg bg-[#F0F2F5] px-2 py-1.5"
        >
          <Avatar :label="personLabel(person)" size="sm" />
          <div class="min-w-0 flex-1">
            <p class="break-all text-xs font-medium leading-snug text-[#111B21]">{{ personLabel(person) }}</p>
            <p class="text-[11px] text-[#667781]">{{ assignment?.assignment_status || 'Assigned' }}</p>
          </div>
          <button
            type="button"
            class="grid size-6 shrink-0 place-items-center rounded-full text-[#667781] hover:bg-white"
            title="Remove assignment"
            @click="handleUnassign(person)"
          >
            <span class="lucide-x size-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>
      <p v-else class="text-xs text-[#667781]">No one assigned yet.</p>
    </div>

    <div class="space-y-1.5 border-t border-[#E9EDEF] px-3 py-2">
      <div class="flex items-center justify-between gap-2">
        <span class="text-[11px] font-semibold uppercase tracking-wide text-[#667781]">
          Linked documents
          <span v-if="links.length" class="font-medium normal-case tracking-normal">({{ links.length }})</span>
        </span>
        <button
          type="button"
          class="text-[11px] font-semibold text-[#00A884] hover:underline"
          @click="promptLink"
        >
          + Link
        </button>
      </div>
      <div v-if="links.length" class="flex flex-col gap-1">
        <component
          :is="canOpen(link.doctype) ? 'button' : 'div'"
          v-for="link in links"
          :key="link.doctype + link.docname"
          :type="canOpen(link.doctype) ? 'button' : undefined"
          class="rounded-md bg-[#F0F2F5] px-2 py-1 text-left text-[11px] leading-snug text-[#111B21]"
          :class="canOpen(link.doctype) ? 'hover:bg-emerald-50' : ''"
          @click="canOpen(link.doctype) && openLinked(link.doctype, link.docname)"
        >
          <span class="font-medium">{{ link.doctype }}:</span>
          {{ link.title || link.docname }}
        </component>
      </div>
      <p v-else class="text-xs leading-snug text-[#667781]">No Frappe records linked yet.</p>
    </div>

    <div class="border-t border-[#E9EDEF] bg-[#F0F2F5]/70 px-3 py-2 text-xs">
      <p class="text-[11px] font-semibold uppercase tracking-wide text-[#667781]">Session</p>
      <p class="mt-1 font-medium" :class="thread.window.status === 'open' ? 'text-emerald-700' : 'text-[#667781]'">
        {{ thread.window.status === 'open' ? '24h window open' : 'Template only' }}
      </p>
      <p class="mt-0.5 break-all text-[11px] text-[#667781]">{{ thread.profile.whatsapp_account }}</p>
    </div>

    <!-- Dialog for Assigning User -->
    <Dialog v-model="assignDialogOpen" title="Assign Conversation" size="md">
      <div class="space-y-4 py-2">
        <p class="text-xs text-ink-gray-6">
          Add a team member. People already assigned stay assigned.
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
