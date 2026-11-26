<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Avatar, Button, Combobox, Dialog, toast } from 'frappe-ui'
import { isManager } from '@/stores/desk'
import { whatsappScreen } from '@/utils/format'
import { displayTitle } from '@/utils/titles'
import { listAssignableUsers } from '@/services/catalogApi'
import {
  addProfileToRecipientList,
  listDirectoryRecipientLists,
  removeProfileFromRecipientList,
  type DirectoryRecipientList,
} from '@/services/directoryApi'
import { userLabel } from '@/utils/frappeSession'
import { errorText } from '@/utils/format'
import { router } from '@/router'
import type { AssignmentInfo, RecipientListRef, Thread } from '@/types'

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

const listDialogOpen = ref(false)
const listOptionsLoading = ref(false)
const listSaving = ref(false)
const availableLists = ref<DirectoryRecipientList[]>([])
const selectedList = ref<string | null>(null)
const listQuery = ref('')
const localRecipientLists = ref<RecipientListRef[]>([])

const removeListDialogOpen = ref(false)
const listToRemove = ref<RecipientListRef | null>(null)
const removingFromList = ref(false)

watch(
  () => [props.thread.profile.name, props.thread.recipient_lists] as const,
  ([, lists]) => {
    localRecipientLists.value = Array.isArray(lists) ? [...lists] : []
  },
  { immediate: true, deep: true },
)

const recipientLists = computed<RecipientListRef[]>(() => localRecipientLists.value)

const selectableListOptions = computed(() => {
  const linked = new Set(recipientLists.value.map((row) => row.name))
  const q = listQuery.value.trim().toLowerCase()
  return availableLists.value
    .filter((row) => !linked.has(row.name))
    .filter((row) => !q || (row.list_name || row.name).toLowerCase().includes(q))
    .map((row) => ({
      value: row.name,
      label: row.list_name || row.name,
      description: `${row.recipient_count} ${row.recipient_count === 1 ? 'recipient' : 'recipients'}`,
    }))
})

async function openAddRecipientList() {
  selectedList.value = null
  listQuery.value = ''
  listDialogOpen.value = true
  listOptionsLoading.value = true
  try {
    const rows = await listDirectoryRecipientLists(props.thread.profile.whatsapp_account)
    availableLists.value = Array.isArray(rows) ? rows : []
  } catch (caught) {
    availableLists.value = []
    toast.error(errorText(caught) || 'Could not load recipient lists.')
  } finally {
    listOptionsLoading.value = false
  }
}

async function submitAddToRecipientList() {
  const listName = selectedList.value?.trim()
  if (!listName) return
  listSaving.value = true
  try {
    const res = await addProfileToRecipientList(props.thread.profile.name, listName)
    const entry: RecipientListRef = {
      name: res.name,
      list_name: res.list_name || res.name,
      whatsapp_account: res.whatsapp_account,
    }
    if (!localRecipientLists.value.some((row) => row.name === entry.name)) {
      localRecipientLists.value = [...localRecipientLists.value, entry]
    }
    toast.success(
      res.added === false
        ? `Already in ${entry.list_name}.`
        : `Added to ${entry.list_name}.`,
    )
    listDialogOpen.value = false
  } catch (caught) {
    toast.error(errorText(caught) || 'Could not add to recipient list.')
  } finally {
    listSaving.value = false
  }
}

function promptRemoveFromList(list: RecipientListRef) {
  listToRemove.value = list
  removeListDialogOpen.value = true
}

async function confirmRemoveFromList() {
  const target = listToRemove.value
  if (!target) return
  removingFromList.value = true
  try {
    await removeProfileFromRecipientList(props.thread.profile.name, target.name)
    localRecipientLists.value = localRecipientLists.value.filter((row) => row.name !== target.name)
    toast.success(`Removed from ${target.list_name || target.name}.`)
    removeListDialogOpen.value = false
    listToRemove.value = null
  } catch (caught) {
    toast.error(errorText(caught) || 'Could not remove from recipient list.')
  } finally {
    removingFromList.value = false
  }
}

function openRecipientList(list: RecipientListRef) {
  void router.push({ path: '/contacts', query: { tab: 'lists', list: list.name } })
}

function openAssign() {
  assignDialogOpen.value = true
}

defineExpose({ openAssign })
</script>

<template>
  <div class="flex flex-col text-[13px] text-ink-gray-9">
    <div class="flex flex-col items-center px-3 py-3 text-center">
      <div class="relative inline-flex">
        <Avatar
          :label="thread.profile.profile_name || thread.profile.phone_number"
          size="2xl"
        />
        <span
          class="absolute bottom-0 right-0 size-3 rounded-full border-2 border-white"
          :class="thread.profile.status === 'Active' ? 'bg-green-500' : 'bg-ink-gray-4'"
          :title="thread.profile.status"
        />
      </div>
      <h2 class="mt-2 text-sm font-semibold leading-snug text-ink-gray-9">
        {{ thread.profile.profile_name || thread.profile.phone_number }}
      </h2>
      <p class="mt-0.5 text-xs text-ink-gray-5">
        {{ thread.profile.phone_number }}
      </p>
    </div>

    <div class="space-y-1.5 border-t border-outline-gray-1 px-3 py-2">
      <div class="flex items-center justify-between gap-2">
        <span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-5">Assigned to</span>
        <button
          type="button"
          class="text-[11px] font-semibold text-ink-gray-8 hover:underline"
          @click="assignDialogOpen = true"
        >
          Assign
        </button>
      </div>
      <div v-if="assignees.length" class="space-y-1">
        <div
          v-for="person in assignees"
          :key="person"
          class="flex items-center gap-2 rounded-lg bg-surface-gray-2 px-2 py-1.5"
        >
          <Avatar :label="personLabel(person)" size="sm" />
          <div class="min-w-0 flex-1">
            <p class="break-all text-xs font-medium leading-snug text-ink-gray-9">{{ personLabel(person) }}</p>
            <p class="text-[11px] text-ink-gray-5">{{ assignment?.assignment_status || 'Assigned' }}</p>
          </div>
          <button
            type="button"
            class="grid size-6 shrink-0 place-items-center rounded-full text-ink-gray-5 hover:bg-white"
            title="Remove assignment"
            @click="handleUnassign(person)"
          >
            <span class="lucide-x size-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>
      <p v-else class="text-xs text-ink-gray-5">No one assigned yet.</p>
    </div>

    <div class="space-y-1.5 border-t border-outline-gray-1 px-3 py-2">
      <div class="flex items-center justify-between gap-2">
        <span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-5">
          Linked documents
          <span v-if="links.length" class="font-medium normal-case tracking-normal">({{ links.length }})</span>
        </span>
        <button
          type="button"
          class="text-[11px] font-semibold text-ink-gray-8 hover:underline"
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
          class="rounded-md bg-surface-gray-2 px-2 py-1 text-left text-[11px] leading-snug text-ink-gray-9"
          :class="canOpen(link.doctype) ? 'hover:bg-surface-gray-3' : ''"
          @click="canOpen(link.doctype) && openLinked(link.doctype, link.docname)"
        >
          <span class="font-medium">{{ link.doctype }}</span>
          <span v-if="displayTitle(link.title, link.docname)"> · {{ displayTitle(link.title, link.docname) }}</span>
        </component>
      </div>
      <p v-else class="text-xs leading-snug text-ink-gray-5">No linked documents yet.</p>
    </div>

    <div class="space-y-1.5 border-t border-outline-gray-1 px-3 py-2">
      <div class="flex items-center justify-between gap-2">
        <span class="text-[11px] font-semibold uppercase tracking-wide text-ink-gray-5">
          Recipient lists
          <span v-if="recipientLists.length" class="font-medium normal-case tracking-normal">({{ recipientLists.length }})</span>
        </span>
        <button
          type="button"
          class="text-[11px] font-semibold text-ink-gray-8 hover:underline"
          title="Add to recipient list"
          @click="openAddRecipientList"
        >
          + Add
        </button>
      </div>
      <div v-if="recipientLists.length" class="flex flex-col gap-1">
        <div
          v-for="list in recipientLists"
          :key="list.name"
          class="flex items-center justify-between gap-1 rounded-md bg-surface-gray-2 px-2 py-1 text-[11px] leading-snug text-ink-gray-9"
        >
          <button
            type="button"
            class="min-w-0 flex-1 truncate text-left font-medium hover:underline"
            @click="openRecipientList(list)"
          >
            {{ list.list_name || list.name }}
          </button>
          <button
            type="button"
            class="grid size-5 shrink-0 place-items-center rounded-full text-ink-gray-5 hover:bg-white hover:text-ink-gray-9"
            title="Remove from recipient list"
            @click="promptRemoveFromList(list)"
          >
            <span class="lucide-x size-3" aria-hidden="true" />
          </button>
        </div>
      </div>
      <p v-else class="text-xs leading-snug text-ink-gray-5">Not in any recipient list yet.</p>
    </div>

    <!-- Dialog for Assigning User -->
    <Dialog v-model="assignDialogOpen" title="Assign conversation" size="md">
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

    <!-- Dialog for Adding to Recipient List -->
    <Dialog v-model="listDialogOpen" title="Add to recipient list" size="md">
      <div class="space-y-4 py-2">
        <p class="text-xs text-ink-gray-6">
          Choose an existing recipient list to add {{ thread.profile.profile_name || thread.profile.phone_number }}.
        </p>
        <Combobox
          v-model="selectedList"
          v-model:query="listQuery"
          :options="selectableListOptions"
          :loading="listOptionsLoading"
          :filterable="false"
          open-on-focus
          placeholder="Select a recipient list"
          empty-text="No available recipient lists found"
        />
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="listDialogOpen = false" />
          <Button
            variant="solid"
            theme="green"
            label="Add"
            :loading="listSaving"
            :disabled="!selectedList"
            @click="submitAddToRecipientList"
          />
        </div>
      </template>
    </Dialog>

    <!-- Dialog for Removing from Recipient List -->
    <Dialog v-model="removeListDialogOpen" title="Remove from recipient list" size="sm">
      <p class="py-2 text-xs text-ink-gray-6">
        Remove {{ thread.profile.profile_name || thread.profile.phone_number }} from
        <span class="font-medium text-ink-gray-9">{{ listToRemove?.list_name || listToRemove?.name }}</span>?
      </p>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="removeListDialogOpen = false" />
          <Button
            variant="solid"
            theme="red"
            label="Remove"
            :loading="removingFromList"
            @click="confirmRemoveFromList"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>
