<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Alert, Badge, Button, call, Checkbox, Dialog, dialog, FormControl, Password, TabButtons, TextInput, toast } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import DeskCard from '@/components/desk/DeskCard.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import DeskTable from '@/components/desk/DeskTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import { errorText } from '@/utils/format'
import { deleteQuickReply, listQuickReplies, saveQuickReply, updateWhatsappAccount } from '@/services/catalogApi'
import { isManager, useDesk } from '@/stores/desk'
import { router } from '@/router'

const desk = useDesk()
const loading = ref(true)
const error = ref<string | null>(null)
const replies = ref<any[]>([])
const activeTab = ref<'replies' | 'hours' | 'routing' | 'profile' | 'team'>('replies')
const searchQuery = ref('')
const isRefreshing = ref(false)
const showCreateModal = ref(false)
const copiedShortcut = ref<string | null>(null)

// Team & Agents State
export interface TeamMember {
  email: string
  full_name: string
  role: 'WhatsApp Manager' | 'WhatsApp User'
  is_owner: boolean
  enabled: boolean
  user_image?: string
  account?: string
}

interface PendingInvite {
  name: string
  email: string
  role: string
  account?: string
}

const teamMembers = ref<TeamMember[]>([])
const pendingInvites = ref<PendingInvite[]>([])
const teamLoading = ref(false)
const teamError = ref<string | null>(null)
const showAddMemberModal = ref(false)
const showEditMemberModal = ref(false)
const editingMember = ref<TeamMember | null>(null)

const inviteEmails = ref('')
const newMemberRole = ref<'WhatsApp User' | 'WhatsApp Manager'>('WhatsApp Manager')
const isSubmittingMember = ref(false)

const editRole = ref<'WhatsApp User' | 'WhatsApp Manager'>('WhatsApp User')
const editEnabled = ref(true)

const fallbackTeamMembers: TeamMember[] = [
  {
    email: 'admin@example.com',
    full_name: 'Administrator (Primary Owner)',
    role: 'WhatsApp Manager',
    is_owner: true,
    enabled: true,
  },
  {
    email: 'agent.rahul@example.com',
    full_name: 'Rahul Sharma',
    role: 'WhatsApp User',
    is_owner: false,
    enabled: true,
  },
  {
    email: 'agent.priya@example.com',
    full_name: 'Priya Patel',
    role: 'WhatsApp User',
    is_owner: false,
    enabled: true,
  },
]

// New Quick Reply Form State
const newTitle = ref('')
const newShortcut = ref('')
const newChannel = ref('')
const newBody = ref('')
const editingReply = ref<string | null>(null)
const replyStatus = ref('Active')
const accountEditor = ref<{
  name: string
  account_name: string
  status: string
  auto_read_receipts: boolean
  is_default: boolean
  phone_id: string
  business_id: string
  app_id: string
  access_token: string
  embedded_signup: boolean
} | null>(null)
const accountEditorOpen = ref(false)

// Enriched sample quick replies for demo/preview mode
const fallbackQuickReplies: any[] = [
  {
    name: 'QR-001',
    title: 'Welcome & Inquiry Greeting',
    shortcut: 'greet',
    whatsapp_account: 'Sundarban Sales',
    status: 'Active',
    usage_count: 42,
    body: 'Hello! Thank you for reaching out to Sundarban Spices. How can we assist you with your whole spice order or lot inquiries today?',
  },
  {
    name: 'QR-002',
    title: 'Weekly Lots & Price Sheet',
    shortcut: 'lots',
    whatsapp_account: 'Sundarban Sales',
    status: 'Active',
    usage_count: 29,
    body: 'Our freshest organic harvest lots of green cardamom, tellicherry black pepper, and pure saffron have arrived from the estate. Reply "SHEET" to receive the lot sheet.',
  },
  {
    name: 'QR-003',
    title: 'Dispatch & Courier Tracking',
    shortcut: 'track',
    whatsapp_account: 'Sundarban Dispatch',
    status: 'Active',
    usage_count: 35,
    body: 'Your shipment has been dispatched from our central hub. You can track live parcel milestones using the tracking link sent in your dispatch confirmation.',
  },
  {
    name: 'QR-004',
    title: 'Support Specialist Handover',
    shortcut: 'support',
    whatsapp_account: 'Sundarban Sales',
    status: 'Active',
    usage_count: 18,
    body: 'A dedicated quality and fulfillment specialist is reviewing your inquiry and will respond within a few moments.',
  },
  {
    name: 'QR-005',
    title: 'Operating Hours Notice',
    shortcut: 'hours',
    whatsapp_account: 'Sundarban Sales',
    status: 'Active',
    usage_count: 11,
    body: 'Our customer support desk is active Monday through Friday from 9:00 AM to 6:00 PM IST. Inquiries outside these hours will be handled first thing next business morning.',
  },
]

function showToast(message: string, isError = false) {
  if (isError) {
    toast.error(message)
  } else {
    toast.success(message)
  }
}

type SettingsTab = 'replies' | 'hours' | 'routing' | 'profile' | 'team'

const tabOptions = computed(() => {
  const tabs: { value: SettingsTab; label: string; iconLeft: string }[] = [
    { value: 'replies', label: 'Quick Replies', iconLeft: 'lucide-message-square' },
  ]
  if (isManager.value) {
    tabs.push(
      { value: 'routing', label: 'Routing & Assignment', iconLeft: 'lucide-route' },
      { value: 'team', label: 'Team & Agents', iconLeft: 'lucide-users' },
      { value: 'profile', label: 'WABA Profile', iconLeft: 'lucide-user' },
    )
  }
  return tabs
})

function selectTab(value: string | number) {
  activeTab.value = value as SettingsTab
  if (value === 'team') loadTeamMembers()
}

function statusTheme(label: string): 'green' | 'red' | 'gray' {
  if (label === 'Active') return 'green'
  if (label === 'Disabled') return 'red'
  return 'gray'
}

const roleOptions = [
  { label: 'WhatsApp Manager', value: 'WhatsApp Manager' },
  { label: 'WhatsApp User (Agent)', value: 'WhatsApp User' },
]
const editRoleOptions = [
  { label: 'WhatsApp User', value: 'WhatsApp User' },
  { label: 'WhatsApp Manager', value: 'WhatsApp Manager' },
]
const statusOptions = [
  { label: 'Active', value: 'Active' },
  { label: 'Inactive', value: 'Inactive' },
]
const accountOptions = computed(() =>
  (desk.inbox.value?.accounts || []).map((account) => ({
    label: account.account_name || account.name,
    value: account.name,
  })),
)
function openIntegrations() {
  void router.push('/integrations')
}

function startReply(row?: any) {
  editingReply.value = row?.name || null
  newTitle.value = row?.title || ''
  newShortcut.value = row?.shortcut || ''
  newBody.value = row?.body || ''
  newChannel.value = desk.account.value || row?.whatsapp_account || ''
  replyStatus.value = row?.status === 'Inactive' ? 'Inactive' : 'Active'
  showCreateModal.value = true
}

async function startAccountEdit(account: any) {
  let source = account
  if (desk.mode.value === 'live') {
    try {
      const rows = await call<any[]>('nudg.desk_api.list_user_accounts')
      source = (rows || []).find((row) => row.name === account.name) || account
    } catch {
      source = account
    }
  }
  accountEditor.value = {
    name: source.name,
    account_name: source.account_name || source.name,
    status: source.status || 'Active',
    auto_read_receipts: Boolean(source.auto_read_receipts),
    is_default: Boolean(source.is_default),
    phone_id: source.phone_id || '',
    business_id: source.business_id || '',
    app_id: source.app_id || '',
    access_token: '',
    embedded_signup: Boolean(Number(source.embedded_signup)),
  }
  accountEditorOpen.value = true
}

async function load() {
  loading.value = true
  error.value = null
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      replies.value = fallbackQuickReplies
      return
    }
    const result = await listQuickReplies(desk.account.value || undefined)
    replies.value = result || []
  } catch (caught) {
    if (!isLive) {
      replies.value = fallbackQuickReplies
    } else {
      error.value = errorText(caught)
      toast.error(error.value)
    }
  } finally {
    loading.value = false
  }
}

async function saveAccount() {
  if (!accountEditor.value || desk.mode.value !== 'live') {
    accountEditor.value = null
    accountEditorOpen.value = false
    return
  }
  try {
    const payload: {
      name: string
      status: string
      auto_read_receipts: number
      is_default: number
      phone_id?: string
      business_id?: string
      app_id?: string
      access_token?: string
    } = {
      name: accountEditor.value.name,
      status: accountEditor.value.status,
      auto_read_receipts: accountEditor.value.auto_read_receipts ? 1 : 0,
      is_default: accountEditor.value.is_default ? 1 : 0,
    }
    if (!accountEditor.value.embedded_signup) {
      payload.phone_id = accountEditor.value.phone_id.trim() || undefined
      payload.business_id = accountEditor.value.business_id.trim() || undefined
      payload.app_id = accountEditor.value.app_id.trim() || undefined
      payload.access_token = accountEditor.value.access_token.trim() || undefined
    }
    await updateWhatsappAccount(payload)
    showToast('WhatsApp account updated.')
    accountEditor.value = null
    accountEditorOpen.value = false
    await desk.load()
  } catch (caught) {
    showToast(errorText(caught), true)
  }
}

async function handleRefresh() {
  isRefreshing.value = true
  try {
    await load()
    showToast('Settings & quick replies refreshed.')
  } finally {
    isRefreshing.value = false
  }
}

async function copyText(text: string, label: string) {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    }
    copiedShortcut.value = label
    showToast(`Copied ${label} to clipboard!`)
    setTimeout(() => {
      if (copiedShortcut.value === label) copiedShortcut.value = null
    }, 2000)
  } catch {
    showToast(`Copied ${label}`)
  }
}

async function handleSaveQuickReply() {
  if (!newTitle.value.trim() || !newBody.value.trim()) {
    showToast('Please enter both a title and message body.')
    return
  }

  const cleanShortcut = newShortcut.value.trim().replace(/^\/+/, '')
  if (desk.mode.value === 'live') {
    try {
      await saveQuickReply({
        name: editingReply.value || undefined,
        title: newTitle.value.trim(),
        shortcut: cleanShortcut || undefined,
        body: newBody.value.trim(),
        whatsapp_account: newChannel.value || undefined,
        status: replyStatus.value,
      })
      showToast(editingReply.value ? `Quick reply "${newTitle.value.trim()}" updated.` : `Quick reply "${newTitle.value.trim()}" created.`)
      newTitle.value = ''
      newShortcut.value = ''
      newBody.value = ''
      editingReply.value = null
      showCreateModal.value = false
      await load()
    } catch (caught) {
      showToast(errorText(caught), true)
    }
    return
  }

  const newRow = {
    name: `QR-${Date.now()}`,
    title: newTitle.value.trim(),
    shortcut: cleanShortcut || undefined,
    whatsapp_account: newChannel.value || 'Sundarban Sales',
    status: 'Active',
    usage_count: 0,
    body: newBody.value.trim(),
  }

  replies.value = [newRow, ...replies.value]
  showToast(`Quick reply "${newRow.title}" created successfully!`)
  newTitle.value = ''
  newShortcut.value = ''
  newBody.value = ''
  showCreateModal.value = false
}

const allReplies = computed(() => replies.value)

const filteredReplies = computed(() => {
  const account = desk.account.value
  return allReplies.value.filter((row) => {
    if (account && row.whatsapp_account && row.whatsapp_account !== account) {
      return false
    }
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      const matchTitle = row.title?.toLowerCase().includes(q)
      const matchShortcut = row.shortcut?.toLowerCase().includes(q)
      const matchBody = row.body?.toLowerCase().includes(q)
      if (!matchTitle && !matchShortcut && !matchBody) return false
    }
    return true
  })
})

const mostUsedReply = computed(() => {
  if (!allReplies.value.length) return null
  return [...allReplies.value].sort((a, b) => (b.usage_count || 0) - (a.usage_count || 0))[0]
})

async function loadTeamMembers() {
  const isLive = Boolean(window.csrf_token)
  teamError.value = null
  if (!isLive) {
    teamMembers.value = fallbackTeamMembers
    pendingInvites.value = []
    return
  }
  teamLoading.value = true
  try {
    const [res, invites] = await Promise.all([
      call('nudg.desk_api.list_team_members'),
      call('nudg.desk_api.list_team_invitations'),
    ])
    teamMembers.value = Array.isArray(res) ? res : []
    pendingInvites.value = Array.isArray(invites) ? invites : []
    if (!Array.isArray(res)) {
      teamError.value = 'Could not load team members.'
      toast.error(teamError.value)
    }
  } catch (caught) {
    teamMembers.value = []
    pendingInvites.value = []
    teamError.value = errorText(caught)
    toast.error(teamError.value)
  } finally {
    teamLoading.value = false
  }
}

const selectedTeamAccount = ref('')

function openInviteModal() {
  inviteEmails.value = ''
  newMemberRole.value = 'WhatsApp Manager'
  selectedTeamAccount.value = desk.account.value || accountOptions.value[0]?.value || ''
  showAddMemberModal.value = true
}

async function handleInviteMembers() {
  const emails = inviteEmails.value.trim()
  if (!emails) {
    showToast('Enter at least one email address.', true)
    return
  }
  const account = selectedTeamAccount.value || desk.inbox.value?.accounts?.[0]?.name || ''
  if (!account) {
    showToast('Choose a WhatsApp account for this invitation.', true)
    return
  }
  isSubmittingMember.value = true
  try {
    const result = await call<any>('nudg.desk_api.invite_team_members', {
      emails,
      role: newMemberRole.value,
      account,
    })
    const invited = result?.invited_emails || []
    const pending = result?.pending_invite_emails || []
    const accepted = result?.accepted_invite_emails || []
    const disabled = result?.disabled_user_emails || []
    if (invited.length) showToast(`Invitation sent to ${invited.join(', ')}. They set their own password from the email.`)
    if (pending.length) showToast(`Already invited: ${pending.join(', ')}`, true)
    if (accepted.length) showToast(`Already joined: ${accepted.join(', ')}`, true)
    if (disabled.length) showToast(`Disabled user: ${disabled.join(', ')}`, true)
    if (!invited.length && !pending.length && !accepted.length && !disabled.length) {
      showToast('No invitations were sent.', true)
    }
    if (invited.length) {
      showAddMemberModal.value = false
      inviteEmails.value = ''
    }
    await loadTeamMembers()
  } catch (err: any) {
    showToast(err?.message || 'Failed to send invitation', true)
  } finally {
    isSubmittingMember.value = false
  }
}

async function resendInvite(invite: PendingInvite) {
  try {
    await call('nudg.desk_api.resend_team_invitation', { name: invite.name })
    showToast(`Invitation resent to ${invite.email}.`)
  } catch (err: any) {
    showToast(err?.message || 'Failed to resend invitation', true)
  }
}

function cancelInvite(invite: PendingInvite) {
  dialog.danger({
    title: 'Cancel invitation?',
    message: `Cancel the invitation to ${invite.email}?`,
    onConfirm: async () => {
      await call('nudg.desk_api.cancel_team_invitation', { name: invite.name })
      showToast('Invitation cancelled.')
      await loadTeamMembers()
    },
  })
}

function openEditMember(member: TeamMember) {
  editingMember.value = member
  editRole.value = member.role
  editEnabled.value = member.enabled
  showEditMemberModal.value = true
}

async function handleUpdateMember() {
  if (!editingMember.value) return
  try {
    const acc = editingMember.value.account || desk.inbox.value?.accounts?.[0]?.name || ''
    await call('nudg.desk_api.update_team_member', {
      account: acc,
      email: editingMember.value.email,
      role: editRole.value,
      enabled: editEnabled.value ? 1 : 0,
    })
    showToast('Team member updated successfully!')
    showEditMemberModal.value = false
    await loadTeamMembers()
  } catch (err: any) {
    showToast(err?.message || 'Failed to update member', true)
  }
}

function removeReply() {
  if (!editingReply.value) return
  const name = editingReply.value
  const label = newTitle.value || name
  dialog.danger({
    title: 'Delete quick reply?',
    message: `Remove “${label}” from this account?`,
    onConfirm: async () => {
      if (desk.mode.value === 'live') {
        await deleteQuickReply(name)
      }
      replies.value = replies.value.filter((row) => row.name !== name)
      editingReply.value = null
      showCreateModal.value = false
      showToast('Quick reply deleted.')
    },
  })
}

watch(
  () => desk.account.value,
  () => {
    void load()
  },
)

onMounted(() => {
  desk.load()
  load()
  loadTeamMembers()
})
</script>

<template>
  <DeskPage variant="scroll">
    <template #actions>
      <Button
        variant="subtle"
        size="sm"
        :loading="isRefreshing"
        icon-left="lucide-refresh-cw"
        label="Refresh"
        @click="handleRefresh"
      />

      <Button
        v-if="isManager"
        variant="solid"
        size="sm"
        class="bg-[#075E54] text-white hover:bg-[#128C7E]"
        label="Integrations"
        @click="openIntegrations"
      />
    </template>

    <template #tabs>
      <TabButtons
        :model-value="activeTab"
        :options="tabOptions"
        variant="underline"
        size="md"
        @update:model-value="selectTab"
      >
        <template #suffix="{ button }">
          <Badge v-if="button.value === 'replies'" theme="gray" size="sm" :label="allReplies.length" />
          <Badge v-else-if="button.value === 'team'" theme="gray" size="sm" :label="teamMembers.length" />
        </template>
      </TabButtons>
    </template>

    <!-- TAB 1: QUICK REPLIES -->
    <div v-if="activeTab === 'replies'" class="space-y-6">
      <DeskEmpty v-if="loading" kind="loading" title="Loading quick replies…" />
      <DeskEmpty v-else-if="error" kind="error" :message="error" allow-retry @retry="load" />
      <template v-else>
      <!-- KPI Metrics -->
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <NumberCard
          title="Configured Shortcuts"
          :value="allReplies.length"
          color="#075E54"
          delta-caption='Triggerable via "/" in composer'
        />
        <NumberCard
          title="Most Used Shortcut"
          :value="'/' + (mostUsedReply?.shortcut || 'greet')"
          color="#075E54"
          :delta-caption="`${mostUsedReply?.usage_count || 0} times · ${mostUsedReply?.title || 'Welcome Greeting'}`"
        />
        <NumberCard
          title="Fast Dispatch Mode"
          value="Freeform & Variables"
          delta-caption="Single-click insertion in Inbox"
        />
      </div>

      <!-- Filter & Search Toolbar -->
      <DeskCard as="div">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <TextInput
            v-model="searchQuery"
            type="text"
            class="w-full sm:w-72"
            placeholder="Search title, /shortcut, body..."
          >
            <template #prefix>
              <span class="lucide-search size-3.5 text-ink-gray-4" />
            </template>
          </TextInput>

          <div class="flex items-center gap-2">
            <Button
              variant="solid"
              size="sm"
              class="bg-[#075E54] text-white hover:bg-[#128C7E]"
              icon-left="lucide-plus"
              label="New Quick Reply"
              @click="startReply()"
            />
          </div>
        </div>
      </DeskCard>

      <!-- Quick Replies Grid -->
      <div v-if="filteredReplies.length > 0" class="grid gap-4 sm:grid-cols-2">
        <DeskCard
          v-for="row in filteredReplies"
          :key="row.name"
          as="article"
          interactive
          class="flex flex-col justify-between"
        >
          <div>
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-center gap-2">
                <Badge v-if="row.shortcut" theme="green" variant="subtle" :label="'/' + row.shortcut" />
                <h3 class="text-sm font-semibold text-ink-gray-9">{{ row.title }}</h3>
              </div>

              <Badge :theme="statusTheme(row.status || 'Active')" :label="row.status || 'Active'" />
            </div>

            <p class="mt-3 text-xs text-ink-gray-7 leading-relaxed whitespace-pre-wrap bg-surface-gray-2/40 rounded-lg p-3 border border-outline-gray-1">
              {{ row.body }}
            </p>
          </div>

          <div class="mt-4 flex items-center justify-between border-t border-outline-gray-1 pt-3 text-xs">
            <div class="flex items-center gap-2 text-ink-gray-5">
              <span>Used {{ row.usage_count || 0 }} times</span>
              <span v-if="row.whatsapp_account">· {{ row.whatsapp_account }}</span>
            </div>

            <div class="flex items-center gap-1">
              <Button
                v-if="isManager"
                variant="ghost"
                size="sm"
                label="Edit"
                @click="startReply(row)"
              />
              <Button
                variant="ghost"
                size="sm"
                :label="copiedShortcut === (row.shortcut ? '/' + row.shortcut : row.title) ? 'Copied!' : 'Copy Text'"
                @click="copyText(row.body, row.shortcut ? '/' + row.shortcut : row.title)"
              />
            </div>
          </div>
        </DeskCard>
      </div>

      <EmptyState
        v-else
        title="No Quick Replies Found"
        description="No replies match the current filter or search criteria."
      >
        <Button
          variant="solid"
          size="sm"
          class="bg-[#075E54] text-white hover:bg-[#128C7E]"
          label="Reset Filters"
          @click="searchQuery = ''"
        />
      </EmptyState>
      </template>
    </div>

    <!-- TAB 2: ROUTING & AUTO-ASSIGNMENT -->
    <div v-else-if="activeTab === 'routing'" class="space-y-6">
      <div class="grid gap-6 sm:grid-cols-3">
        <DeskCard>
          <div class="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
            <span class="lucide-users size-5" />
          </div>
          <h3 class="text-sm font-semibold text-ink-gray-9">Frappe Assignment Rules</h3>
          <p class="mt-1 text-xs text-ink-gray-6 leading-relaxed">
            Assign conversations from the inbox, and add agents from the Team tab.
          </p>
          <Button
            v-if="isManager"
            class="mt-3"
            variant="ghost"
            size="sm"
            label="Open team"
            @click="selectTab('team')"
          />
        </DeskCard>

        <DeskCard>
          <div class="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
            <span class="lucide-shield-check size-5" />
          </div>
          <h3 class="text-sm font-semibold text-ink-gray-9">Agent Role & Permissions</h3>
          <p class="mt-1 text-xs text-ink-gray-6 leading-relaxed">
            Users with the <code class="rounded bg-surface-gray-2 px-1 text-[11px]">WhatsApp User</code> role can chat with assigned leads and view shared inboxes. Administrators require <code class="rounded bg-surface-gray-2 px-1 text-[11px]">System Manager</code>.
          </p>
        </DeskCard>

        <DeskCard>
          <div class="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-purple-50 text-purple-600">
            <span class="lucide-clock size-5" />
          </div>
          <h3 class="text-sm font-semibold text-ink-gray-9">24h SLA Session Window</h3>
          <p class="mt-1 text-xs text-ink-gray-6 leading-relaxed">
            Meta enforces a 24-hour service window per conversation. Inbound replies automatically re-open the freeform window for support agents.
          </p>
        </DeskCard>
      </div>
    </div>

    <!-- TAB 4: WABA PROFILE -->
    <div v-else-if="activeTab === 'profile'" class="space-y-6">
      <template v-if="desk.mode.value === 'live'">
        <Alert
          v-if="!(desk.inbox.value?.accounts || []).length"
          theme="gray"
          title="No WhatsApp account is connected yet."
          description="Add one from Integrations."
        />
        <DeskCard
          v-for="account in desk.inbox.value?.accounts || []"
          :key="account.name"
        >
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 class="text-lg font-bold text-ink-gray-9">{{ account.account_name || 'WhatsApp account' }}</h2>
              <p class="mt-1 text-xs text-ink-gray-5">{{ account.status }}</p>
              <p v-if="account.is_default" class="mt-1 text-xs font-medium text-[#075E54]">Default number</p>
            </div>
            <Button
              v-if="isManager"
              variant="subtle"
              size="sm"
              label="Edit"
              @click="startAccountEdit(account)"
            />
          </div>
        </DeskCard>
      </template>
      <DeskCard v-else>
        <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between border-b border-outline-gray-2 pb-5">
          <div class="flex items-start gap-4">
            <div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-[#075E54] text-white shadow-sm font-bold text-xl">
              SS
            </div>
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <h2 class="text-lg font-bold text-ink-gray-9">Sundarban Spices & Agri Corp</h2>
                <Badge theme="green" variant="subtle" label="Meta Verified Business" />
              </div>
              <p class="mt-1 text-xs text-ink-gray-5">Official WhatsApp Business Account</p>
            </div>
          </div>

          <Button
            v-if="isManager"
            variant="subtle"
            size="sm"
            label="Connect a number"
            @click="openIntegrations"
          />
        </div>

        <div class="mt-5 grid gap-4 sm:grid-cols-2 text-xs">
          <div>
            <span class="font-semibold text-ink-gray-5">Business Category</span>
            <p class="mt-1 text-ink-gray-9 font-medium">Food & Beverage · Organic Spices & Grocery</p>
          </div>

          <div>
            <span class="font-semibold text-ink-gray-5">Meta Messaging Tier</span>
            <p class="mt-1 text-emerald-700 font-bold">Tier 1 · 10,000 unique recipients / 24h</p>
          </div>

          <div class="col-span-2">
            <span class="font-semibold text-ink-gray-5">Business Description</span>
            <p class="mt-1 text-ink-gray-9 leading-relaxed">
              Direct farm-to-table organic whole spices, premium single-origin cardamom, tellicherry black peppercorns, and artisanal spice gift packaging from the Sundarban valley reserves.
            </p>
          </div>

          <div>
            <span class="font-semibold text-ink-gray-5">Official Website</span>
            <p class="mt-1 font-mono text-ink-gray-9">https://sundarbanspices.example.com</p>
          </div>

          <div>
            <span class="font-semibold text-ink-gray-5">Physical Address</span>
            <p class="mt-1 text-ink-gray-9">Sundarban Organic Estate, South 24 Parganas, West Bengal 743370, India</p>
          </div>
        </div>
      </DeskCard>
    </div>

    <!-- TAB 5: TEAM & AGENTS -->
    <div v-else-if="activeTab === 'team'" class="space-y-6">
      <DeskCard
        title="Team Members & Agents"
        description="Invite people by email. They set their own password from the invitation, the same way Frappe CRM does."
      >
        <template #actions>
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Invite"
            icon-left="lucide-user-plus"
            @click="openInviteModal"
          />
        </template>

        <div v-if="pendingInvites.length" class="mb-4">
          <p class="mb-2 text-xs font-semibold text-ink-gray-5">Pending invitations</p>
          <div
            v-for="invite in pendingInvites"
            :key="invite.name"
            class="flex items-center justify-between gap-3 border-b border-outline-gray-1 py-2 last:border-b-0"
          >
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-ink-gray-9">{{ invite.email }}</p>
              <p class="text-[11px] text-ink-gray-5">{{ invite.role }}<span v-if="invite.account"> · {{ invite.account }}</span></p>
            </div>
            <div class="flex shrink-0 gap-1">
              <Button variant="subtle" size="sm" label="Resend" @click="resendInvite(invite)" />
              <Button variant="subtle" size="sm" label="Cancel" @click="cancelInvite(invite)" />
            </div>
          </div>
        </div>

        <DeskEmpty v-if="teamLoading" kind="loading" title="Loading team members…" />
        <DeskEmpty v-else-if="teamError" kind="error" :message="teamError" allow-retry @retry="loadTeamMembers" />
        <DeskEmpty
          v-else-if="!teamMembers.length"
          title="No team members yet"
          description="Invite an agent. They join from the email and choose their own password."
        />

        <!-- Members Table -->
        <DeskTable v-else>
          <template #head>
            <tr>
              <th class="px-4 py-3 font-semibold">Agent</th>
              <th class="px-4 py-3 font-semibold">Role</th>
              <th class="px-4 py-3 font-semibold">WhatsApp Account</th>
              <th class="px-4 py-3 font-semibold">Status</th>
              <th class="px-4 py-3 text-right font-semibold">Action</th>
            </tr>
          </template>
          <tr v-for="member in teamMembers" :key="member.email" class="hover:bg-surface-gray-1">
            <td class="px-4 py-3">
              <div class="flex items-center gap-3">
                <div class="flex h-8 w-8 items-center justify-center rounded-full bg-[#075E54]/10 text-xs font-bold text-[#075E54]">
                  {{ member.full_name?.charAt(0) || 'U' }}
                </div>
                <div>
                  <p class="font-semibold text-ink-gray-9">{{ member.full_name }}</p>
                  <p class="text-[11px] text-ink-gray-5 font-mono">{{ member.email }}</p>
                </div>
              </div>
            </td>
            <td class="px-4 py-3">
              <Badge :theme="member.role === 'WhatsApp Manager' ? 'violet' : 'blue'" :label="member.role" />
            </td>
            <td class="px-4 py-3 text-ink-gray-7 font-medium">
              {{ member.account || 'All Permitted' }}
            </td>
            <td class="px-4 py-3">
              <Badge :theme="member.enabled ? 'green' : 'red'" :label="member.enabled ? 'Active' : 'Disabled'" />
            </td>
            <td class="px-4 py-3 text-right">
              <Button
                v-if="!member.is_owner"
                variant="ghost"
                size="sm"
                label="Edit"
                @click="openEditMember(member)"
              />
              <span v-else class="text-ink-gray-4 text-[11px]">Owner</span>
            </td>
          </tr>
        </DeskTable>
      </DeskCard>
    </div>

    <Dialog
      v-model="showAddMemberModal"
      title="Invite users"
      size="xl"
    >
      <div class="space-y-4 py-1">
        <p class="-mt-2 text-xs text-ink-gray-6">
          Send an invitation email. They set their own password from that email and land in Nudg. Separate multiple addresses with commas. WhatsApp Manager is the default, and that role also includes WhatsApp User.
        </p>

        <FormControl
          v-model="inviteEmails"
          type="textarea"
          label="Email addresses"
          placeholder="agent@example.com, manager@example.com"
          required
        />

        <FormControl
          v-model="newMemberRole"
          type="select"
          label="Role"
          :options="roleOptions"
        />
      </div>

      <template #actions>
        <div class="flex items-center justify-between w-full">
          <Button
            variant="subtle"
            label="Cancel"
            @click="showAddMemberModal = false"
          />
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            :loading="isSubmittingMember"
            label="Send invitation"
            @click="handleInviteMembers"
          />
        </div>
      </template>
    </Dialog>

    <!-- MODAL: Edit Team Member -->
    <Dialog
      v-model="showEditMemberModal"
      :title="editingMember ? 'Edit Member · ' + editingMember.full_name : 'Edit Member'"
      size="lg"
    >
      <div v-if="editingMember" class="space-y-4 py-1">
        <FormControl
          v-model="editRole"
          type="select"
          label="Role"
          :options="editRoleOptions"
        />
        <Checkbox v-model="editEnabled" label="Account Enabled" />
      </div>

      <template #actions>
        <div class="flex items-center justify-between w-full">
          <Button
            variant="subtle"
            label="Cancel"
            @click="showEditMemberModal = false"
          />
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            label="Save Changes"
            @click="handleUpdateMember"
          />
        </div>
      </template>
    </Dialog>

    <!-- MODAL: Edit WhatsApp account -->
    <Dialog v-model="accountEditorOpen" :title="accountEditor ? 'Edit ' + accountEditor.account_name : 'WhatsApp account'">
      <div v-if="accountEditor" class="space-y-4 py-1">
        <p v-if="accountEditor.embedded_signup" class="text-xs text-ink-gray-6">
          Connected with Embedded Signup. Business ID, phone number ID, app ID, and the access token come from Meta and cannot be changed.
        </p>
        <p v-else class="text-xs text-ink-gray-6">A new number is connected from Integrations. Update the credentials Meta issued for this number. Leave the token blank to keep the current one.</p>
        <FormControl
          v-model="accountEditor.phone_id"
          type="text"
          label="Phone number ID"
          :disabled="accountEditor.embedded_signup"
        />
        <FormControl
          v-model="accountEditor.business_id"
          type="text"
          label="Business ID"
          :disabled="accountEditor.embedded_signup"
        />
        <FormControl
          v-model="accountEditor.app_id"
          type="text"
          label="App ID"
          :disabled="accountEditor.embedded_signup"
        />
        <Password
          v-if="!accountEditor.embedded_signup"
          v-model="accountEditor.access_token"
          label="Access token"
          placeholder="Leave blank to keep the current token"
        />
        <p v-else class="text-xs text-ink-gray-6">The access token is stored from Embedded Signup.</p>
        <FormControl
          v-model="accountEditor.status"
          type="select"
          label="Status"
          :options="statusOptions"
        />
        <Checkbox v-model="accountEditor.is_default" label="Default account" />
        <p class="-mt-2 text-xs text-ink-gray-6">The first number you connect is the default. Later numbers stay optional until you check this. Inbox and assignment use the default among the numbers assigned to each person.</p>
        <Checkbox v-model="accountEditor.auto_read_receipts" label="Send read receipts" />
      </div>
      <template #actions>
        <div class="flex w-full justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="accountEditorOpen = false" />
          <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Save" @click="saveAccount" />
        </div>
      </template>
    </Dialog>

    <!-- MODAL: Create New Quick Reply -->
    <Dialog
      v-model="showCreateModal"
      title="Quick Reply"
      size="xl"
    >
      <div class="space-y-4 py-1">
        <p class="-mt-2 text-xs text-ink-gray-6">
          Create a keyboard shortcut for fast customer replies in conversation threads
        </p>

        <FormControl
          v-model="newTitle"
          type="text"
          label="Title"
          placeholder="e.g. Return Policy Notice"
        />

        <div class="grid grid-cols-2 gap-3">
          <FormControl
            v-model="newShortcut"
            type="text"
            label="Keyboard Shortcut"
            placeholder="return"
          >
            <template #prefix>
              <span class="font-mono text-ink-gray-4">/</span>
            </template>
          </FormControl>
          <FormControl
            v-model="replyStatus"
            type="select"
            label="Status"
            :options="statusOptions"
          />
        </div>

        <FormControl
          v-model="newBody"
          type="textarea"
          label="Message Body"
          :rows="4"
          placeholder="Type message text to be inserted in the conversation composer..."
        />
      </div>

      <template #actions>
        <div class="flex items-center justify-between w-full">
          <div class="flex gap-2">
            <Button
              variant="subtle"
              label="Cancel"
              @click="showCreateModal = false"
            />
            <Button
              v-if="editingReply"
              variant="subtle"
              label="Delete"
              @click="removeReply"
            />
          </div>
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            :label="editingReply ? 'Save Quick Reply' : 'Create Quick Reply'"
            @click="handleSaveQuickReply"
          />
        </div>
      </template>
    </Dialog>
  </DeskPage>
</template>
