<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMediaQuery } from '@vueuse/core'
import { Alert, Avatar, Button, Checkbox, Dialog, FormControl, TabButtons, TextInput, toast } from 'frappe-ui'
import { router } from '@/router'
import {
  deleteDirectoryProfile,
  deleteDirectoryRecipientList,
  fetchDirectoryAccess,
  getDirectoryRecipientList,
  listDirectoryProfiles,
  listDirectoryRecipientLists,
  saveDirectoryProfile,
  saveDirectoryRecipientList,
  type DirectoryProfile,
  type DirectoryRecipient,
  type DirectoryRecipientList,
} from '@/services/directoryApi'
import { useDesk } from '@/stores/desk'
import { accountArg } from '@/utils/accountSelection'
import { bootDirectoryAccess, type DirectoryAccess, type DocAccess } from '@/utils/directoryAccess'
import DeskCard from '@/components/desk/DeskCard.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import DeskSplit from '@/components/desk/DeskSplit.vue'
import { errorText, rawErrorText } from '@/utils/format'

const desk = useDesk()
const narrow = useMediaQuery('(max-width: 767px)')
const live = Boolean(window.csrf_token)
const emptyAccess = (): DocAccess => ({ read: false, write: false, create: false, delete: false })
const previewAccess = (): DocAccess => ({ read: true, write: true, create: true, delete: true })

const access = ref<DirectoryAccess>(
  bootDirectoryAccess() || {
    profile: live ? emptyAccess() : previewAccess(),
    recipient_list: live ? emptyAccess() : previewAccess(),
  },
)

type Tab = 'contacts' | 'lists'
const tab = ref<Tab>('contacts')
const query = ref('')
const loading = ref(true)
const loadedOnce = ref(false)
const accessReady = ref(!live || Boolean(bootDirectoryAccess()))
const accessError = ref('')
const saving = ref(false)
const profiles = ref<DirectoryProfile[]>([])
const lists = ref<DirectoryRecipientList[]>([])
const selectedName = ref<string | null>(null)
const creating = ref(false)
const confirmDelete = ref(false)

const profileForm = ref({
  name: '',
  profile_name: '',
  phone_number: '',
  whatsapp_account: '',
  status: 'Active',
})
const listForm = ref({
  name: '',
  list_name: '',
  description: '',
  whatsapp_account: '',
  recipients: [] as DirectoryRecipient[],
})

const statusOptions = [
  { label: 'Active', value: 'Active' },
  { label: 'Blocked', value: 'Blocked' },
  { label: 'Archived', value: 'Archived' },
]

const accountOptions = computed(() =>
  (desk.inbox.value?.accounts || []).map((row) => ({
    label: row.account_name || row.name,
    value: row.name,
  })),
)
const listAccountOptions = computed(() => [{ label: 'Any account', value: '' }, ...accountOptions.value])

const profileAccess = computed(() => access.value.profile)
const listAccess = computed(() => access.value.recipient_list)
const canSeeAny = computed(() => profileAccess.value.read || listAccess.value.read)
const activeAccess = computed(() => (tab.value === 'contacts' ? profileAccess.value : listAccess.value))
const canCreate = computed(() => activeAccess.value.create)
const tabOptions = computed(() => {
  const options: Array<{ label: string; value: Tab }> = []
  if (profileAccess.value.read) options.push({ label: 'Contacts', value: 'contacts' })
  if (listAccess.value.read) options.push({ label: 'Recipient lists', value: 'lists' })
  return options
})
const formLocked = computed(() => (creating.value ? !activeAccess.value.create : !activeAccess.value.write))

const visibleProfiles = computed(() => profiles.value)
const visibleLists = computed(() => lists.value)

function defaultAccount() {
  const selected = accountArg(desk.account.value)
  if (selected) return selected
  return accountOptions.value[0]?.value || ''
}

function blankProfile() {
  profileForm.value = {
    name: '',
    profile_name: '',
    phone_number: '',
    whatsapp_account: defaultAccount(),
    status: 'Active',
  }
}

function blankList() {
  listForm.value = {
    name: '',
    list_name: '',
    description: '',
    whatsapp_account: defaultAccount(),
    recipients: [],
  }
}

function applyProfile(row: DirectoryProfile) {
  profileForm.value = {
    name: row.name,
    profile_name: row.profile_name || '',
    phone_number: row.phone_number || '',
    whatsapp_account: row.whatsapp_account || defaultAccount(),
    status: row.status || 'Active',
  }
}

function applyList(row: DirectoryRecipientList) {
  listForm.value = {
    name: row.name,
    list_name: row.list_name || row.name,
    description: row.description || '',
    whatsapp_account: row.whatsapp_account || '',
    recipients: (row.recipients || []).map((recipient) => ({
      mobile_number: recipient.mobile_number || '',
      recipient_name: recipient.recipient_name || '',
      unsubscribed: recipient.unsubscribed ? 1 : 0,
    })),
  }
}

async function loadAccess() {
  if (!live) {
    accessReady.value = true
    return
  }
  accessError.value = ''
  try {
    const row = await fetchDirectoryAccess()
    if (row?.profile && row?.recipient_list) access.value = row
    else accessError.value = 'Contacts permissions did not load.'
  } catch (caught) {
    const message = rawErrorText(caught)
    accessError.value =
      message && message !== 'Catalog product could not be sent.'
        ? message
        : 'Contacts permissions did not load.'
  } finally {
    accessReady.value = true
  }
}

async function loadRecords() {
  if (!live) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const account = accountArg(desk.account.value)
    if (profileAccess.value.read) {
      const rows = await listDirectoryProfiles(account, query.value.trim())
      profiles.value = Array.isArray(rows) ? rows : []
    } else {
      profiles.value = []
    }
    if (listAccess.value.read) {
      const rows = await listDirectoryRecipientLists(account, query.value.trim())
      lists.value = Array.isArray(rows) ? rows : []
    } else {
      lists.value = []
    }
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    loading.value = false
    loadedOnce.value = true
  }
}

function pickTab(next: string | number) {
  const value = String(next)
  if (value !== 'contacts' && value !== 'lists') return
  if (value === 'contacts' && !profileAccess.value.read) return
  if (value === 'lists' && !listAccess.value.read) return
  tab.value = value
  creating.value = false
  selectedName.value = null
}

function startCreate() {
  if (!canCreate.value) return
  creating.value = true
  selectedName.value = null
  if (tab.value === 'contacts') blankProfile()
  else blankList()
}

async function selectProfile(row: DirectoryProfile) {
  creating.value = false
  selectedName.value = row.name
  applyProfile(row)
}

async function selectList(row: DirectoryRecipientList) {
  creating.value = false
  selectedName.value = row.name
  applyList(row)
  if (!live) return
  try {
    const full = await getDirectoryRecipientList(row.name)
    if (full?.name) applyList(full)
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

function addRecipient() {
  if (formLocked.value) return
  listForm.value.recipients.push({ mobile_number: '', recipient_name: '', unsubscribed: 0 })
}

function setUnsubscribed(recipient: DirectoryRecipient, value: boolean | string | number | undefined) {
  recipient.unsubscribed = value === true || value === 1 || value === '1' ? 1 : 0
}

async function retryLoad() {
  await loadAccess()
  await loadRecords()
}

function removeRecipient(index: number) {
  if (formLocked.value) return
  listForm.value.recipients.splice(index, 1)
}

async function save() {
  if (formLocked.value) return
  if (!live) {
    toast.error('Sign in on a Frappe site to save this record.')
    return
  }
  saving.value = true
  try {
    if (tab.value === 'contacts') {
      const saved = await saveDirectoryProfile({
        name: profileForm.value.name || undefined,
        profile_name: profileForm.value.profile_name.trim(),
        phone_number: profileForm.value.phone_number.trim(),
        whatsapp_account: profileForm.value.whatsapp_account,
        status: profileForm.value.status,
      })
      toast.success(saved.created ? 'Contact created.' : 'Contact saved.')
      creating.value = false
      selectedName.value = saved.name
      await loadRecords()
      const row = profiles.value.find((item) => item.name === saved.name)
      applyProfile(row || saved)
    } else {
      const saved = await saveDirectoryRecipientList({
        name: listForm.value.name || undefined,
        list_name: listForm.value.list_name.trim(),
        description: listForm.value.description.trim(),
        whatsapp_account: listForm.value.whatsapp_account || undefined,
        recipients: listForm.value.recipients.filter((row) => row.mobile_number.trim() || row.recipient_name.trim()),
      })
      toast.success(saved.created ? 'Recipient list created.' : 'Recipient list saved.')
      creating.value = false
      selectedName.value = saved.name
      await loadRecords()
      applyList(saved)
    }
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    saving.value = false
  }
}

async function removeRecord() {
  if (!live || !selectedName.value || !activeAccess.value.delete) return
  saving.value = true
  try {
    if (tab.value === 'contacts') await deleteDirectoryProfile(selectedName.value)
    else await deleteDirectoryRecipientList(selectedName.value)
    toast.success(tab.value === 'contacts' ? 'Contact deleted.' : 'Recipient list deleted.')
    confirmDelete.value = false
    creating.value = false
    selectedName.value = null
    await loadRecords()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    saving.value = false
  }
}

async function openChat() {
  const name = profileForm.value.name
  if (!name) return
  await router.push('/conversations')
  await desk.openProfile(name)
}

let searchTimer = 0
watch(query, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => void loadRecords(), 200)
})

watch(
  () => desk.account.value,
  () => void loadRecords(),
)

onMounted(async () => {
  await loadAccess()
  if (!profileAccess.value.read && listAccess.value.read) tab.value = 'lists'
  await loadRecords()
})

const showDetail = computed(() => creating.value || Boolean(selectedName.value))
const detailTitle = computed(() => {
  if (tab.value === 'contacts') {
    if (creating.value) return 'New contact'
    return profileForm.value.profile_name || profileForm.value.phone_number || 'Contact'
  }
  if (creating.value) return 'New recipient list'
  return listForm.value.list_name || 'Recipient list'
})
</script>

<template>
  <DeskPage variant="studio">
    <template #actions>
      <div class="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <TabButtons
          v-if="tabOptions.length"
          :model-value="tab"
          :options="tabOptions"
          variant="underline"
          @update:model-value="pickTab"
        />
        <div class="ml-auto flex items-center justify-end gap-2">
          <Button variant="subtle" size="sm" icon="lucide-refresh-cw" label="Refresh" :loading="loading" @click="loadRecords" />
          <Button
            v-if="canCreate"
            variant="solid"
            size="sm"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            icon-left="lucide-plus"
            :label="tab === 'contacts' ? 'New contact' : 'New list'"
            @click="startCreate"
          />
        </div>
      </div>
    </template>

    <DeskEmpty v-if="!accessReady || (loading && !loadedOnce)" kind="loading" title="Loading contacts…" />
    <DeskEmpty
      v-else-if="accessError && !canSeeAny"
      kind="error"
      title="Contacts could not be loaded"
      :message="accessError"
      allow-retry
      @retry="retryLoad"
    />
    <DeskEmpty
      v-else-if="!canSeeAny"
      title="No access to this directory"
      description="Role Permission Manager decides who can see contacts and recipient lists. Ask a System Manager to grant read permission."
    />

    <DeskSplit
      v-else
      :show-detail="showDetail"
      :narrow="narrow"
      columns="minmax(16rem, 22rem) minmax(0, 1fr)"
    >
      <template #master>
        <div class="border-b border-outline-gray-2 p-3">
          <TextInput
            v-model="query"
            class="w-full"
            :placeholder="tab === 'contacts' ? 'Search name or phone' : 'Search recipient lists'"
          >
            <template #prefix>
              <span class="lucide-search size-3.5 text-ink-gray-4" />
            </template>
          </TextInput>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto">
          <template v-if="tab === 'contacts'">
            <DeskEmpty v-if="!visibleProfiles.length" compact title="No contacts yet" description="Create a contact when your role can add records." />
            <button
              v-for="row in visibleProfiles"
              :key="row.name"
              type="button"
              class="flex w-full items-center gap-3 border-b border-outline-gray-1 px-3 py-3 text-left hover:bg-surface-gray-1"
              :class="selectedName === row.name ? 'bg-surface-gray-2' : ''"
              @click="selectProfile(row)"
            >
              <Avatar :label="row.profile_name || row.phone_number" size="lg" />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold text-ink-gray-9">{{ row.profile_name || row.phone_number }}</span>
                <span class="block truncate text-xs text-ink-gray-5">{{ row.phone_number }}</span>
              </span>
            </button>
          </template>
          <template v-else>
            <DeskEmpty v-if="!visibleLists.length" compact title="No recipient lists yet" />
            <button
              v-for="row in visibleLists"
              :key="row.name"
              type="button"
              class="flex w-full items-center gap-3 border-b border-outline-gray-1 px-3 py-3 text-left hover:bg-surface-gray-1"
              :class="selectedName === row.name ? 'bg-surface-gray-2' : ''"
              @click="selectList(row)"
            >
              <Avatar :label="row.list_name || row.name" size="lg" />
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold text-ink-gray-9">{{ row.list_name || row.name }}</span>
                <span class="block truncate text-xs text-ink-gray-5">
                  {{ row.recipient_count }} {{ row.recipient_count === 1 ? 'recipient' : 'recipients' }}
                </span>
              </span>
            </button>
          </template>
        </div>
      </template>

      <template #detail>
        <DeskEmpty
          v-if="!showDetail"
          :title="tab === 'contacts' ? 'Select a contact' : 'Select a recipient list'"
          :description="canCreate ? 'Use New contact or New list, or open a record from the list.' : 'You can view these records. Create and edit follow your role permissions.'"
        />
        <form v-else class="flex min-h-0 flex-1 flex-col overflow-y-auto p-4" @submit.prevent="save">
          <div v-if="narrow" class="mb-3">
            <Button variant="ghost" size="sm" icon-left="lucide-arrow-left" label="Back" @click="creating = false; selectedName = null" />
          </div>
          <DeskCard :title="detailTitle">
            <template #actions>
              <Button
                v-if="!creating && activeAccess.delete && selectedName"
                type="button"
                size="sm"
                variant="subtle"
                theme="red"
                label="Delete"
                @click="confirmDelete = true"
              />
              <Button
                v-if="tab === 'contacts' && profileForm.name"
                type="button"
                size="sm"
                variant="subtle"
                label="Open chat"
                @click="openChat"
              />
              <Button
                v-if="!formLocked"
                type="submit"
                size="sm"
                variant="solid"
                class="bg-[#075E54] text-white hover:bg-[#128C7E]"
                :label="creating ? 'Create' : 'Save'"
                :loading="saving"
              />
            </template>

            <Alert v-if="formLocked" class="mb-4" theme="amber" title="View only">
              Role Permission Manager has not granted {{ creating ? 'create' : 'write' }} permission.
            </Alert>

            <div v-if="tab === 'contacts'" class="grid max-w-xl gap-3">
              <FormControl v-model="profileForm.profile_name" type="text" label="Name" placeholder="Contact name" :disabled="formLocked" />
              <FormControl v-model="profileForm.phone_number" type="text" label="Phone number" placeholder="+91…" :disabled="formLocked" />
              <FormControl
                v-model="profileForm.whatsapp_account"
                type="select"
                label="WhatsApp account"
                :options="accountOptions"
                :disabled="formLocked"
              />
              <FormControl
                v-model="profileForm.status"
                type="select"
                label="Status"
                :options="statusOptions"
                :disabled="formLocked"
              />
            </div>

            <div v-else class="grid gap-3">
              <FormControl v-model="listForm.list_name" type="text" label="List name" placeholder="VIP customers" :disabled="formLocked" />
              <FormControl
                v-model="listForm.description"
                type="textarea"
                label="Description"
                placeholder="Who is on this list"
                :rows="2"
                :disabled="formLocked"
              />
              <FormControl
                v-model="listForm.whatsapp_account"
                type="select"
                label="WhatsApp account"
                :options="listAccountOptions"
                :disabled="formLocked"
              />

              <div class="mt-1 overflow-hidden rounded-lg border border-outline-gray-2">
                <div class="flex items-center justify-between border-b border-outline-gray-2 bg-surface-gray-1 px-3 py-2">
                  <p class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Recipients</p>
                  <Button v-if="!formLocked" type="button" variant="ghost" size="sm" label="Add recipient" icon-left="lucide-plus" @click="addRecipient" />
                </div>
                <p v-if="!listForm.recipients.length" class="px-3 py-6 text-center text-xs text-ink-gray-5">No recipients on this list.</p>
                <div
                  v-for="(recipient, index) in listForm.recipients"
                  :key="index"
                  class="grid gap-3 border-b border-outline-gray-1 px-3 py-3 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto_auto] sm:items-end"
                >
                  <FormControl v-model="recipient.recipient_name" type="text" label="Name" placeholder="Name" :disabled="formLocked" />
                  <FormControl v-model="recipient.mobile_number" type="text" label="Mobile" placeholder="Mobile" :disabled="formLocked" />
                  <Checkbox
                    class="mb-2"
                    label="Unsubscribed"
                    :model-value="Boolean(recipient.unsubscribed)"
                    :disabled="formLocked"
                    @update:model-value="setUnsubscribed(recipient, $event)"
                  />
                  <Button
                    v-if="!formLocked"
                    type="button"
                    class="mb-1"
                    variant="ghost"
                    size="sm"
                    icon="lucide-x"
                    label="Remove"
                    @click="removeRecipient(index)"
                  />
                </div>
              </div>
            </div>
          </DeskCard>
        </form>
      </template>
    </DeskSplit>

    <Dialog v-model="confirmDelete" :title="tab === 'contacts' ? 'Delete contact' : 'Delete recipient list'">
      <p class="text-sm text-ink-gray-7">
        {{
          tab === 'contacts'
            ? 'This removes the contact. Messages already sent stay in the inbox.'
            : 'This removes the recipient list. Campaigns that already used it are left as they are.'
        }}
      </p>
      <template #actions>
        <Button label="Cancel" @click="confirmDelete = false" />
        <Button variant="solid" theme="red" label="Delete" :loading="saving" @click="removeRecord" />
      </template>
    </Dialog>
  </DeskPage>
</template>
