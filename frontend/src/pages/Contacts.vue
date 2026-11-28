<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Checkbox,
  Dialog,
  Dropdown,
  FileUploader,
  FormControl,
  ItemListRow,
  TabButtons,
  TextInput,
  toast,
} from 'frappe-ui'
import { router } from '@/router'
import {
  deleteDirectoryProfile,
  deleteDirectoryRecipientList,
  fetchDirectoryAccess,
  getDirectoryRecipientList,
  importDirectoryProfiles,
  listDirectoryProfiles,
  listDirectoryRecipientLists,
  saveDirectoryProfile,
  saveDirectoryRecipientList,
  type DirectoryImportResult,
  type DirectoryProfile,
  type DirectoryRecipient,
  type DirectoryRecipientList,
} from '@/services/directoryApi'
import { useDesk } from '@/stores/desk'
import { accountArg } from '@/utils/accountSelection'
import { bootDirectoryAccess, type DirectoryAccess, type DocAccess } from '@/utils/directoryAccess'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import { errorText, rawErrorText } from '@/utils/format'

const desk = useDesk()
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
const profileDialogOpen = ref(false)
const listDialogOpen = ref(false)
const importDialogOpen = ref(false)
const importFileUrl = ref('')
const importFileName = ref('')
const importing = ref(false)
const importResult = ref<DirectoryImportResult | null>(null)
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

const currentAccount = computed(() => accountArg(desk.account.value) || '')

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
  return currentAccount.value
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
  if (tab.value === 'contacts') {
    blankProfile()
    profileDialogOpen.value = true
  } else {
    blankList()
    listDialogOpen.value = true
  }
}

async function selectProfile(row: DirectoryProfile) {
  creating.value = false
  selectedName.value = row.name
  applyProfile(row)
  profileDialogOpen.value = true
}

function statusTheme(status?: string): 'green' | 'red' | 'gray' {
  if (status === 'Active') return 'green'
  if (status === 'Blocked') return 'red'
  return 'gray'
}

async function selectList(row: DirectoryRecipientList) {
  creating.value = false
  selectedName.value = row.name
  applyList(row)
  listDialogOpen.value = true
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
  const account = defaultAccount()
  if (!account) {
    toast.error('Select a WhatsApp number in the top bar first.')
    return
  }
  saving.value = true
  try {
    if (tab.value === 'contacts') {
      const saved = await saveDirectoryProfile({
        name: profileForm.value.name || undefined,
        profile_name: profileForm.value.profile_name.trim(),
        phone_number: profileForm.value.phone_number.trim(),
        whatsapp_account: account,
        status: profileForm.value.status,
      })
      toast.success(saved.created ? 'Contact created.' : 'Contact saved.')
      creating.value = false
      selectedName.value = saved.name
      profileDialogOpen.value = false
      await loadRecords()
      const row = profiles.value.find((item) => item.name === saved.name)
      applyProfile(row || saved)
    } else {
      const saved = await saveDirectoryRecipientList({
        name: listForm.value.name || undefined,
        list_name: listForm.value.list_name.trim(),
        description: listForm.value.description.trim(),
        whatsapp_account: account,
        recipients: listForm.value.recipients.filter((row) => row.mobile_number.trim() || row.recipient_name.trim()),
      })
      toast.success(saved.created ? 'Recipient list created.' : 'Recipient list saved.')
      creating.value = false
      selectedName.value = saved.name
      listDialogOpen.value = false
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
    profileDialogOpen.value = false
    listDialogOpen.value = false
    creating.value = false
    selectedName.value = null
    await loadRecords()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    saving.value = false
  }
}

async function openChat(targetName?: string) {
  const name = targetName || profileForm.value.name
  if (!name) return
  profileDialogOpen.value = false
  await router.push('/conversations')
  await desk.openProfile(name)
}

function openImportContacts() {
  if (!live) {
    toast.error('Sign in on a Frappe site to import contacts.')
    return
  }
  importFileUrl.value = ''
  importFileName.value = ''
  importResult.value = null
  importDialogOpen.value = true
}

function downloadImportTemplate() {
  const csv = 'Profile Name,Phone Number\nAnanya Sharma,+919812345678\n'
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'contacts_template.csv'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function onImportUploaded(file: { file_url?: string; file_name?: string }) {
  importFileUrl.value = file?.file_url || ''
  importFileName.value = file?.file_name || ''
  importResult.value = null
}

async function runImportContacts() {
  const account = defaultAccount()
  if (!account) {
    toast.error('Select a WhatsApp number in the top bar first.')
    return
  }
  if (!importFileUrl.value) {
    toast.error('Upload a CSV or Excel file first.')
    return
  }
  importing.value = true
  try {
    const res = await importDirectoryProfiles(importFileUrl.value, account)
    importResult.value = res
    await loadRecords()
    toast.success(`Imported: ${res.created} created, ${res.updated} updated.`)
    if (!res.failed) {
      importDialogOpen.value = false
    }
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    importing.value = false
  }
}

function exportContacts(fileFormat: 'CSV' | 'Excel') {
  if (!live) {
    toast.error('Sign in on a Frappe site to export contacts.')
    return
  }
  const filters: Array<[string, string, string, string]> = []
  if (currentAccount.value) {
    filters.push(['WA Profile', 'whatsapp_account', '=', currentAccount.value])
  }
  const form = document.createElement('form')
  form.method = 'POST'
  form.action = '/api/method/frappe.desk.reportview.export_query'
  form.target = '_blank'
  form.style.display = 'none'

  const fields: Record<string, string> = {
    doctype: 'WA Profile',
    file_format_type: fileFormat,
    fields: JSON.stringify(['name', 'profile_name', 'phone_number', 'whatsapp_account', 'status']),
    filters: JSON.stringify(filters),
    order_by: '`tabWA Profile`.`modified` desc',
    with_comment_count: '0',
    csrf_token: window.csrf_token || '',
  }

  for (const [key, value] of Object.entries(fields)) {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = key
    input.value = value
    form.appendChild(input)
  }

  document.body.appendChild(form)
  form.submit()
  document.body.removeChild(form)
}

const exportOptions = [
  { label: 'Export CSV', onClick: () => exportContacts('CSV') },
  { label: 'Export Excel', onClick: () => exportContacts('Excel') },
]

let searchTimer = 0
watch(query, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => void loadRecords(), 200)
})

watch(
  () => desk.account.value,
  () => {
    creating.value = false
    selectedName.value = null
    void loadRecords()
  },
)

onMounted(async () => {
  await loadAccess()
  const routeQuery = router.currentRoute.value.query
  const requestedTab = typeof routeQuery.tab === 'string' ? routeQuery.tab : ''
  const requestedList = typeof routeQuery.list === 'string' ? routeQuery.list : ''
  if (requestedTab === 'lists' && listAccess.value.read) tab.value = 'lists'
  else if (!profileAccess.value.read && listAccess.value.read) tab.value = 'lists'
  await loadRecords()
  if (tab.value === 'lists' && requestedList) {
    const match = lists.value.find((row) => row.name === requestedList)
    if (match) await selectList(match)
  }
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
        <div class="flex flex-wrap items-center justify-end gap-2 sm:ml-auto">
          <Button
            v-if="tab === 'contacts' && profileAccess.create"
            variant="subtle"
            size="sm"
            icon-left="lucide-upload"
            label="Import"
            @click="openImportContacts"
          />
          <Dropdown v-if="tab === 'contacts' && profileAccess.read" :options="exportOptions">
            <Button variant="subtle" size="sm" icon-left="lucide-download" icon-right="lucide-chevron-down" label="Export" />
          </Dropdown>
          <Button variant="subtle" size="sm" icon="lucide-refresh-cw" label="Refresh" :loading="loading" @click="loadRecords" />
          <Button v-if="canCreate" variant="solid" theme="green" size="sm" icon-left="lucide-plus" :label="tab === 'contacts' ? 'New contact' : 'New list'" @click="startCreate"/>
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
      title="No access to contacts"
      description="You don't have permission to view contacts or recipient lists. Ask an administrator for access."
    />

    <div v-else-if="tab === 'contacts'" class="flex min-h-0 flex-1 flex-col overflow-hidden p-4">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <TextInput
          v-model="query"
          class="w-full max-w-sm"
          placeholder="Search name or phone"
        >
          <template #prefix>
            <span class="lucide-search size-3.5 text-ink-gray-4" />
          </template>
        </TextInput>
        <Badge :label="`${visibleProfiles.length} ${visibleProfiles.length === 1 ? 'contact' : 'contacts'}`" variant="subtle" theme="gray" />
      </div>

      <DeskEmpty
        v-if="!visibleProfiles.length"
        title="No contacts yet"
        description="Create a contact or receive a message to see profiles here."
      />

      <div v-else class="min-h-0 flex-1 overflow-y-auto rounded-lg border border-outline-gray-2 bg-surface-base divide-y divide-outline-gray-1">
        <ItemListRow
          v-for="row in visibleProfiles"
          :key="row.name"
          as="div"
          size="lg"
          class="px-3 py-2.5 hover:bg-surface-gray-1"
        >
          <template #prefix>
            <Avatar :label="row.profile_name || row.phone_number" size="md" />
          </template>
          <template #label>
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-ink-gray-9">
                {{ row.profile_name || row.phone_number }}
              </p>
              <p class="truncate text-xs text-ink-gray-5">{{ row.phone_number }}</p>
            </div>
          </template>
          <template #suffix>
            <div class="flex shrink-0 items-center gap-1 sm:gap-1.5">
              <Badge :label="row.status || 'Active'" variant="subtle" :theme="statusTheme(row.status)" size="sm" />
              <Button
                variant="ghost"
                size="sm"
                icon="lucide-message-square"
                title="Open chat"
                @click="openChat(row.name)"
              />
              <Button
                variant="ghost"
                size="sm"
                icon="lucide-pencil"
                title="Edit contact"
                @click="selectProfile(row)"
              />
            </div>
          </template>
        </ItemListRow>
      </div>
    </div>

    <div v-else class="flex min-h-0 flex-1 flex-col overflow-hidden p-4">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
        <TextInput
          v-model="query"
          class="w-full max-w-sm"
          placeholder="Search recipient lists"
        >
          <template #prefix>
            <span class="lucide-search size-3.5 text-ink-gray-4" />
          </template>
        </TextInput>
        <Badge :label="`${visibleLists.length} ${visibleLists.length === 1 ? 'list' : 'lists'}`" variant="subtle" theme="gray" />
      </div>

      <DeskEmpty
        v-if="!visibleLists.length"
        title="No recipient lists yet"
        description="Create a recipient list to group contacts for campaigns."
      />

      <div v-else class="min-h-0 flex-1 overflow-y-auto rounded-lg border border-outline-gray-2 bg-surface-base divide-y divide-outline-gray-1">
        <ItemListRow
          v-for="row in visibleLists"
          :key="row.name"
          as="div"
          size="lg"
          class="px-3 py-2.5 hover:bg-surface-gray-1"
        >
          <template #prefix>
            <Avatar :label="row.list_name || row.name" size="md" />
          </template>
          <template #label>
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-ink-gray-9">
                {{ row.list_name || row.name }}
              </p>
              <p v-if="row.description" class="truncate text-xs text-ink-gray-5">{{ row.description }}</p>
            </div>
          </template>
          <template #suffix>
            <div class="flex shrink-0 items-center gap-1 sm:gap-1.5">
              <Badge
                :label="`${row.recipient_count} ${row.recipient_count === 1 ? 'recipient' : 'recipients'}`"
                variant="subtle"
                theme="gray"
                size="sm"
              />
              <Button
                variant="ghost"
                size="sm"
                icon="lucide-pencil"
                title="Edit recipient list"
                @click="selectList(row)"
              />
            </div>
          </template>
        </ItemListRow>
      </div>
    </div>

    <Dialog v-model="profileDialogOpen" :title="creating ? 'New contact' : (profileForm.profile_name || profileForm.phone_number || 'Edit contact')" size="md">
      <form class="space-y-3 py-1" @submit.prevent="save">
        <Alert v-if="formLocked" theme="amber" title="View only">
          You don't have permission to {{ creating ? 'create' : 'edit' }} this contact.
        </Alert>
        <Alert v-else-if="!currentAccount" theme="amber" title="No account selected">
          Select a WhatsApp number in the top bar before saving.
        </Alert>
        <FormControl v-model="profileForm.profile_name" type="text" label="Name" placeholder="Contact name" :disabled="formLocked" />
        <FormControl v-model="profileForm.phone_number" type="text" label="Phone number" placeholder="+91…" :disabled="formLocked" />
        <FormControl
          v-model="profileForm.status"
          type="select"
          label="Status"
          :options="statusOptions"
          :disabled="formLocked"
        />
      </form>
      <template #actions>
        <div class="flex w-full items-center justify-between gap-2">
          <Button
            v-if="!creating && activeAccess.delete && selectedName"
            type="button"
            size="sm"
            variant="subtle"
            theme="red"
            label="Delete"
            @click="confirmDelete = true"
          />
          <div class="ml-auto flex items-center gap-2">
            <Button type="button" size="sm" variant="subtle" label="Cancel" @click="profileDialogOpen = false" />
            <Button
              v-if="!formLocked"
              type="button"
              size="sm"
              variant="solid"
              theme="green"
              loading-text="Saving…"
              :label="creating ? 'Create' : 'Save'"
              :loading="saving"
              @click="save"
            />
          </div>
        </div>
      </template>
    </Dialog>

    <Dialog v-model="listDialogOpen" :title="creating ? 'New recipient list' : (listForm.list_name || 'Edit recipient list')" size="xl">
      <form class="space-y-3 py-1" @submit.prevent="save">
        <Alert v-if="formLocked" theme="amber" title="View only">
          You don't have permission to {{ creating ? 'create' : 'edit' }} this recipient list.
        </Alert>
        <Alert v-else-if="!currentAccount" theme="amber" title="No account selected">
          Select a WhatsApp number in the top bar before saving.
        </Alert>
        <FormControl v-model="listForm.list_name" type="text" label="List name" placeholder="VIP customers" :disabled="formLocked" />
        <FormControl
          v-model="listForm.description"
          type="textarea"
          label="Description"
          placeholder="Who is on this list"
          :rows="2"
          :disabled="formLocked"
        />
        <div class="overflow-hidden rounded-lg border border-outline-gray-2">
          <div class="flex items-center justify-between border-b border-outline-gray-2 bg-surface-gray-1 px-3 py-2">
            <p class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5">Recipients</p>
            <Button v-if="!formLocked" type="button" variant="ghost" size="sm" label="Add recipient" icon-left="lucide-plus" @click="addRecipient" />
          </div>
          <div class="max-h-64 overflow-y-auto">
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
      </form>
      <template #actions>
        <div class="flex w-full items-center justify-between gap-2">
          <Button
            v-if="!creating && activeAccess.delete && selectedName"
            type="button"
            size="sm"
            variant="subtle"
            theme="red"
            label="Delete"
            @click="confirmDelete = true"
          />
          <div class="ml-auto flex items-center gap-2">
            <Button type="button" size="sm" variant="subtle" label="Cancel" @click="listDialogOpen = false" />
            <Button
              v-if="!formLocked"
              type="button"
              size="sm"
              variant="solid"
              theme="green"
              loading-text="Saving…"
              :label="creating ? 'Create' : 'Save'"
              :loading="saving"
              @click="save"
            />
          </div>
        </div>
      </template>
    </Dialog>

    <Dialog v-model="importDialogOpen" title="Import contacts" size="md">
      <div class="space-y-4 py-1">
        <Alert v-if="!currentAccount" theme="amber" title="No account selected">
          Select a WhatsApp number in the top bar before importing.
        </Alert>
        <div class="flex items-center justify-between gap-2 rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5">
          <div class="min-w-0">
            <p class="text-xs font-medium text-ink-gray-9">CSV or Excel format</p>
            <p class="text-[11px] text-ink-gray-6">Columns: Profile Name, Phone Number</p>
          </div>
          <Button
            type="button"
            variant="subtle"
            size="sm"
            icon-left="lucide-download"
            label="Template"
            @click="downloadImportTemplate"
          />
        </div>
        <FileUploader
          :file-types="['.csv', '.xlsx', '.xls']"
          @success="onImportUploaded"
        >
          <template #default="{ openFileSelector, uploading, progress }">
            <div class="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-outline-gray-3 bg-surface-gray-1 px-4 py-6 text-center">
              <span class="lucide-upload size-5 text-ink-gray-5" aria-hidden="true" />
              <p v-if="importFileName" class="text-xs font-medium text-ink-gray-9">{{ importFileName }}</p>
              <p v-else class="text-xs text-ink-gray-6">Upload a CSV or Excel file with contact names and phone numbers.</p>
              <Button
                type="button"
                variant="subtle"
                size="sm"
                :loading="uploading"
                :label="uploading ? `Uploading ${progress}%` : (importFileName ? 'Replace file' : 'Choose file')"
                @click="openFileSelector"
              />
            </div>
          </template>
        </FileUploader>
        <Alert v-if="importResult && importResult.failed" theme="amber" :title="`${importResult.failed} rows failed`">
          <ul class="mt-1 space-y-0.5 text-[11px]">
            <li v-for="err in importResult.errors" :key="err.row">
              Row {{ err.row }} ({{ err.phone || 'empty' }}): {{ err.error }}
            </li>
          </ul>
        </Alert>
      </div>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button type="button" size="sm" variant="subtle" label="Cancel" @click="importDialogOpen = false" />
          <Button
            type="button"
            size="sm"
            variant="solid"
            theme="green"
            label="Import"
            :loading="importing"
            :disabled="!importFileUrl || !currentAccount"
            @click="runImportContacts"
          />
        </div>
      </template>
    </Dialog>

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
