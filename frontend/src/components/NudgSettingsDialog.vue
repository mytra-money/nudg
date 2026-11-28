<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  FormControl,
  ItemListRow,
  KeyboardShortcut,
  SettingsBody,
  SettingsContent,
  SettingsDialog,
  SettingsHeader,
  SettingsNavGroup,
  SettingsNavItem,
  SettingsPanel,
  SettingsRow,
  SettingsSidebar,
  Switch,
  TextInput,
  call,
  toast,
} from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import {
  deleteQuickReply,
  getChatbot,
  listQuickReplies,
  saveChatbot,
  saveQuickReply,
  updateWhatsappAccount,
} from '@/services/catalogApi'
import { isManager, useDesk } from '@/stores/desk'
import { accountArg } from '@/utils/accountSelection'
import { errorText } from '@/utils/format'
import { sessionUser as readSessionUser } from '@/utils/frappeSession'

export type SettingsDialogTab =
  | 'profile'
  | 'appearance'
  | 'preferences'
  | 'users'
  | 'accounts'
  | 'replies'
  | 'routing'
  | 'automation'
  | 'integrations'

const open = defineModel<boolean>('open', { default: false })
const activeTab = defineModel<SettingsDialogTab>('tab', { default: 'replies' })

const emit = defineEmits<{
  connectAccount: []
}>()

const router = useRouter()
const desk = useDesk()
const sessionUser = readSessionUser() || 'Guest'
const sessionSite = window.sitename || 'Local preview'

// Quick Replies (list + inline create/edit/delete)
const replies = ref<any[]>([])
const repliesLoading = ref(false)
const replySearch = ref('')
const copiedShortcut = ref<string | null>(null)
const replyFormOpen = ref(false)
const replySaving = ref(false)
const replyForm = ref({
  name: '',
  title: '',
  shortcut: '',
  status: 'Active',
  body: '',
})

const filteredReplies = computed(() => {
  const q = replySearch.value.trim().toLowerCase()
  if (!q) return replies.value
  return replies.value.filter(
    (r) =>
      (r.title || '').toLowerCase().includes(q) ||
      (r.shortcut || '').toLowerCase().includes(q) ||
      (r.body || '').toLowerCase().includes(q),
  )
})

function startReplyEdit(row?: any) {
  replyForm.value = {
    name: row?.name || '',
    title: row?.title || '',
    shortcut: row?.shortcut || '',
    status: row?.status === 'Inactive' ? 'Inactive' : 'Active',
    body: row?.body || '',
  }
  replyFormOpen.value = true
}

async function submitReply() {
  const title = replyForm.value.title.trim()
  const body = replyForm.value.body.trim()
  if (!title || !body) {
    toast.error('Title and message body are required.')
    return
  }
  if (desk.mode.value !== 'live') {
    toast.info('Preview mode: changes are not saved to a live Frappe site.')
    replyFormOpen.value = false
    return
  }
  replySaving.value = true
  try {
    await saveQuickReply({
      name: replyForm.value.name || undefined,
      title,
      shortcut: replyForm.value.shortcut.trim().replace(/^\/+/, ''),
      status: replyForm.value.status,
      body,
      whatsapp_account: accountArg(desk.account.value) || undefined,
    })
    toast.success(replyForm.value.name ? 'Quick reply updated' : 'Quick reply created')
    replyFormOpen.value = false
    await loadReplies()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    replySaving.value = false
  }
}

async function removeReply(row: any) {
  if (desk.mode.value !== 'live' || !row?.name) return
  try {
    await deleteQuickReply(row.name)
    toast.success('Quick reply deleted')
    await loadReplies()
  } catch (caught) {
    toast.error(errorText(caught))
  }
}

async function loadReplies() {
  repliesLoading.value = true
  try {
    if (!window.csrf_token) {
      replies.value = [
        {
          name: 'QR-001',
          title: 'Welcome & Inquiry Greeting',
          shortcut: 'greet',
          status: 'Active',
          body: 'Hello! Thank you for reaching out. How can we assist you today?',
        },
      ]
      return
    }
    replies.value = (await listQuickReplies(desk.account.value || undefined)) || []
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    repliesLoading.value = false
  }
}

async function copyShortcut(text: string, label: string) {
  try {
    await navigator.clipboard.writeText(text)
    copiedShortcut.value = label
    toast.success(`Copied ${label}`)
    setTimeout(() => {
      if (copiedShortcut.value === label) copiedShortcut.value = null
    }, 1800)
  } catch {
    toast.error('Could not copy to clipboard.')
  }
}

// Users / Team & Agents + Inline Invite
interface TeamMember {
  email: string
  full_name: string
  role: string
  is_owner?: boolean
  enabled?: boolean
}
const teamMembers = ref<TeamMember[]>([])
const teamLoading = ref(false)
const inviteOpen = ref(false)
const inviteEmails = ref('')
const inviteRole = ref<'WhatsApp Manager' | 'WhatsApp User'>('WhatsApp User')
const inviteSubmitting = ref(false)

async function loadTeam() {
  if (!isManager.value || !window.csrf_token) return
  const account = accountArg(desk.account.value) || ''
  if (!account) {
    teamMembers.value = []
    return
  }
  teamLoading.value = true
  try {
    const res = await call<TeamMember[]>('nudg.desk_api.list_team_members', { account })
    teamMembers.value = Array.isArray(res) ? res : []
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    teamLoading.value = false
  }
}

async function submitInvite() {
  const emails = inviteEmails.value.trim()
  const account = accountArg(desk.account.value) || ''
  if (!emails) {
    toast.error('Enter at least one email address.')
    return
  }
  if (!account) {
    toast.error('Select a WhatsApp account from the left rail first.')
    return
  }
  inviteSubmitting.value = true
  try {
    const result = await call<any>('nudg.desk_api.invite_team_members', {
      emails,
      role: inviteRole.value,
      account,
    })
    const invited = result?.invited_emails || []
    if (invited.length) {
      toast.success(`Invitation sent to ${invited.join(', ')}`)
      inviteEmails.value = ''
      inviteOpen.value = false
      await loadTeam()
    } else {
      toast.info('No new invitations were sent (users may already be invited or joined).')
    }
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    inviteSubmitting.value = false
  }
}

// Automation & AI config
const botLoading = ref(false)
const botSaving = ref(false)
const botLoadedAccount = ref<string | null>(null)
const botForm = ref({
  enabled: false,
  business_hours_only: false,
  out_of_hours_message: '',
  default_response: '',
  enable_ai: false,
  ai_provider: '',
  ai_model: '',
  session_timeout_minutes: 30,
})

const providerOptions = [
  { label: 'Select provider', value: '' },
  { label: 'OpenAI', value: 'OpenAI' },
  { label: 'Anthropic', value: 'Anthropic' },
  { label: 'Google', value: 'Google' },
  { label: 'Custom', value: 'Custom' },
]

async function loadBot() {
  if (!isManager.value) return
  const account = accountArg(desk.account.value) || ''
  if (!account || !window.csrf_token) {
    botLoadedAccount.value = account
    return
  }
  botLoading.value = true
  try {
    const data = await getChatbot(account)
    botForm.value = {
      enabled: Boolean(data?.enabled),
      business_hours_only: Boolean(data?.business_hours_only),
      out_of_hours_message: data?.out_of_hours_message || '',
      default_response: data?.default_response || '',
      enable_ai: Boolean(data?.enable_ai),
      ai_provider: data?.ai_provider || '',
      ai_model: data?.ai_model || '',
      session_timeout_minutes: Number(data?.session_timeout_minutes || 30),
    }
    botLoadedAccount.value = account
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    botLoading.value = false
  }
}

async function submitBot() {
  const account = accountArg(desk.account.value) || ''
  if (!account || desk.mode.value !== 'live') {
    toast.info('Select a live WhatsApp account to save automation settings.')
    return
  }
  botSaving.value = true
  try {
    await saveChatbot(account, {
      enabled: botForm.value.enabled ? 1 : 0,
      business_hours_only: botForm.value.business_hours_only ? 1 : 0,
      out_of_hours_message: botForm.value.out_of_hours_message,
      default_response: botForm.value.default_response,
      enable_ai: botForm.value.enable_ai ? 1 : 0,
      ai_provider: botForm.value.ai_provider,
      ai_model: botForm.value.ai_model,
      session_timeout_minutes: Number(botForm.value.session_timeout_minutes || 30),
    })
    toast.success('Automation settings saved')
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    botSaving.value = false
  }
}

// Account quick toggles
const savingAccount = ref<string | null>(null)
async function toggleReadReceipts(account: any, next: boolean) {
  if (desk.mode.value !== 'live') return
  savingAccount.value = account.name
  try {
    await updateWhatsappAccount({
      name: account.name,
      status: account.status || 'Active',
      auto_read_receipts: next ? 1 : 0,
      is_default: account.is_default ? 1 : 0,
    })
    toast.success(
      `Read receipts ${next ? 'enabled' : 'disabled'} for ${account.account_name || account.name}`,
    )
    await desk.load()
  } catch (caught) {
    toast.error(errorText(caught))
  } finally {
    savingAccount.value = null
  }
}

// Local preferences
const PREF_SOUND_KEY = 'nudg.pref.sound'
const PREF_COMPACT_KEY = 'nudg.pref.compact'
const soundEnabled = ref(
  typeof localStorage !== 'undefined' ? localStorage.getItem(PREF_SOUND_KEY) !== '0' : true,
)
const compactList = ref(
  typeof localStorage !== 'undefined' ? localStorage.getItem(PREF_COMPACT_KEY) === '1' : false,
)

watch(soundEnabled, (val) => {
  try {
    localStorage.setItem(PREF_SOUND_KEY, val ? '1' : '0')
  } catch {
    /* ignore */
  }
})
watch(compactList, (val) => {
  try {
    localStorage.setItem(PREF_COMPACT_KEY, val ? '1' : '0')
  } catch {
    /* ignore */
  }
})

function openRoute(path: string) {
  open.value = false
  void router.push(path)
}

watch(
  () => desk.account.value,
  () => {
    replies.value = []
    teamMembers.value = []
    botLoadedAccount.value = null
  },
)

watch(open, (isOpen) => {
  if (!isOpen) return
  if (activeTab.value === 'replies' && !replies.value.length) void loadReplies()
  if (activeTab.value === 'users' && !teamMembers.value.length) void loadTeam()
  if (activeTab.value === 'automation' && botLoadedAccount.value === null) void loadBot()
})

watch(activeTab, (tab) => {
  if (!open.value) return
  if (tab === 'replies' && !replies.value.length) void loadReplies()
  if (tab === 'users' && !teamMembers.value.length) void loadTeam()
  if (tab === 'automation' && botLoadedAccount.value === null) void loadBot()
})
</script>

<template>
  <SettingsDialog v-model:open="open" v-model:tab="activeTab" size="4xl">
    <template #title>Nudg Settings</template>
    <template #description>
      Configure profile, preferences, team users, WhatsApp accounts, quick replies, and automation.
    </template>

    <SettingsSidebar>
      <div class="mb-2 flex items-center justify-between px-2 sm:hidden">
        <span class="text-sm font-semibold text-ink-gray-9">Settings</span>
        <Button variant="ghost" size="sm" icon="lucide-x" aria-label="Close settings" @click="open = false" />
      </div>
      <SettingsNavGroup label="Settings">
        <SettingsNavItem value="profile">
          <template #prefix>
            <Avatar :label="sessionUser" size="xs" />
          </template>
          Profile
        </SettingsNavItem>
        <SettingsNavItem value="appearance">
          <template #prefix>
            <span class="lucide-palette size-4 text-ink-gray-6" aria-hidden="true" />
          </template>
          Appearance
        </SettingsNavItem>
        <SettingsNavItem value="preferences">
          <template #prefix>
            <span class="lucide-sliders-horizontal size-4 text-ink-gray-6" aria-hidden="true" />
          </template>
          Preferences
        </SettingsNavItem>
      </SettingsNavGroup>

      <SettingsNavGroup label="Workspace">
        <SettingsNavItem v-if="isManager" value="users">
          <template #prefix>
            <span class="lucide-users size-4 text-ink-gray-6" aria-hidden="true" />
          </template>
          Users
        </SettingsNavItem>
        <SettingsNavItem v-if="isManager" value="accounts">
          <template #prefix>
            <span class="lucide-smartphone size-4 text-ink-gray-6" aria-hidden="true" />
          </template>
          WABA Accounts
        </SettingsNavItem>
        <SettingsNavItem value="replies">
          <template #prefix>
            <span class="lucide-zap size-4 text-ink-gray-6" aria-hidden="true" />
          </template>
          Quick Replies
        </SettingsNavItem>
        <SettingsNavItem v-if="isManager" value="routing">
          <template #prefix>
            <span class="lucide-route size-4 text-ink-gray-6" aria-hidden="true" />
          </template>
          Routing & SLA
        </SettingsNavItem>
      </SettingsNavGroup>

      <SettingsNavGroup v-if="isManager" label="Integrations">
        <SettingsNavItem value="automation">
          <template #prefix>
            <span class="lucide-bot size-4 text-ink-gray-6" aria-hidden="true" />
          </template>
          Automation & AI
        </SettingsNavItem>
        <SettingsNavItem value="integrations">
          <template #prefix>
            <span class="lucide-plug size-4 text-ink-gray-6" aria-hidden="true" />
          </template>
          Connected Apps
        </SettingsNavItem>
      </SettingsNavGroup>
    </SettingsSidebar>

    <SettingsContent>
      <!-- PROFILE -->
      <SettingsPanel value="profile">
        <SettingsHeader title="Profile" description="Your active Frappe session and desk role." />
        <SettingsBody>
          <div class="mt-4 divide-y divide-outline-gray-1">
            <SettingsRow title="Signed in user" :description="sessionSite">
              <div class="flex items-center gap-2">
                <Avatar :label="sessionUser" size="sm" />
                <span class="text-sm font-medium text-ink-gray-9">{{ sessionUser }}</span>
              </div>
            </SettingsRow>
            <SettingsRow
              title="Desk access"
              description="Permissions determine whether you can manage accounts, campaigns, and team members."
            >
              <Badge
                :theme="isManager ? 'green' : 'gray'"
                variant="subtle"
                :label="isManager ? 'WhatsApp Manager' : 'WhatsApp User'"
              />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- APPEARANCE -->
      <SettingsPanel value="appearance">
        <SettingsHeader
          title="Appearance"
          description="Customize how conversations and lists are displayed."
        />
        <SettingsBody>
          <div class="mt-4 divide-y divide-outline-gray-1">
            <SettingsRow
              title="Compact conversation list"
              description="Show denser rows in the inbox conversation sidebar."
            >
              <Switch v-model="compactList" />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- PREFERENCES -->
      <SettingsPanel value="preferences">
        <SettingsHeader
          title="Preferences"
          description="Notification behavior and keyboard shortcuts."
        />
        <SettingsBody>
          <div class="mt-4 divide-y divide-outline-gray-1">
            <SettingsRow
              title="Message sound alerts"
              description="Play a subtle chime when a new inbound WhatsApp message arrives."
            >
              <Switch v-model="soundEnabled" />
            </SettingsRow>
            <SettingsRow title="Quick Jump" description="Search conversations or jump to any page.">
              <KeyboardShortcut :keys="['Meta', 'K']" />
            </SettingsRow>
            <SettingsRow title="Open settings dialog" description="Toggle this settings modal.">
              <KeyboardShortcut :keys="['Meta', 'Shift', ',']" />
            </SettingsRow>
            <SettingsRow title="Toggle sidebar" description="Collapse or expand navigation.">
              <KeyboardShortcut :keys="['Meta', 'B']" />
            </SettingsRow>
            <SettingsRow title="Insert quick reply" description="Type slash in the chat composer.">
              <KeyboardShortcut :keys="['/']" />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- USERS (with inline Invite) -->
      <SettingsPanel v-if="isManager" value="users">
        <SettingsHeader
          title="Users"
          description="Manage agents and managers with access to the selected WhatsApp account."
        >
          <template #actions>
            <Button
              variant="solid"
              theme="green"
              size="sm"
              icon-left="lucide-user-plus"
              :label="inviteOpen ? 'Close' : 'Invite User'"
              @click="inviteOpen = !inviteOpen"
            />
          </template>
        </SettingsHeader>
        <SettingsBody>
          <div class="mt-5 space-y-4">
            <div v-if="inviteOpen" class="space-y-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4">
              <FormControl
                v-model="inviteEmails"
                type="text"
                label="Email addresses"
                placeholder="agent@example.com, manager@example.com"
              />
              <div class="flex flex-wrap items-end gap-3">
                <FormControl
                  v-model="inviteRole"
                  type="select"
                  label="Role"
                  class="min-w-48 flex-1"
                  :options="[
                    { label: 'WhatsApp User', value: 'WhatsApp User' },
                    { label: 'WhatsApp Manager', value: 'WhatsApp Manager' },
                  ]"
                />
                <Button
                  variant="solid"
                  theme="green"
                  size="sm"
                  :loading="inviteSubmitting"
                  label="Send Invitation"
                  @click="submitInvite"
                />
              </div>
            </div>

            <div v-if="teamLoading" class="py-8 text-center text-xs text-ink-gray-5">
              Loading team members…
            </div>
            <EmptyState
              v-else-if="!teamMembers.length"
              compact
              title="No team members loaded"
              description="Select a WhatsApp account from the left rail or invite a new agent."
            />
            <div v-else class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
              <ItemListRow
                v-for="member in teamMembers"
                :key="member.email"
                as="div"
                size="md"
                class="px-3.5 py-2.5"
              >
                <template #prefix>
                  <Avatar :label="member.full_name || member.email" size="sm" />
                </template>
                <template #label>
                  <div class="min-w-0">
                    <p class="truncate text-sm font-medium text-ink-gray-9">{{ member.full_name }}</p>
                    <p class="truncate font-mono text-[11px] text-ink-gray-5">{{ member.email }}</p>
                  </div>
                </template>
                <template #suffix>
                  <Badge
                    :theme="member.role === 'WhatsApp Manager' ? 'violet' : 'blue'"
                    :label="member.role"
                    size="sm"
                  />
                </template>
              </ItemListRow>
            </div>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- WABA ACCOUNTS -->
      <SettingsPanel v-if="isManager" value="accounts">
        <SettingsHeader
          title="WABA Accounts"
          description="Connected WhatsApp Business numbers and read-receipt behavior."
        >
          <template #actions>
            <Button
              variant="solid"
              theme="green"
              size="sm"
              icon-left="lucide-plus"
              label="Connect Number"
              @click="emit('connectAccount')"
            />
          </template>
        </SettingsHeader>
        <SettingsBody>
          <div class="mt-5 space-y-4">
            <Alert
              v-if="!(desk.inbox.value?.accounts || []).length"
              theme="amber"
              title="No WhatsApp account connected"
              description="Connect a number to start sending and receiving live messages."
            />
            <div v-else class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2 px-4">
              <SettingsRow
                v-for="account in desk.inbox.value?.accounts || []"
                :key="account.name"
                :title="account.account_name || account.name"
                :description="`Status: ${account.status || 'Active'}${account.is_default ? ' · Default number' : ''} · Auto read receipts`"
              >
                <Switch
                  :model-value="Boolean(account.auto_read_receipts)"
                  :disabled="savingAccount === account.name || desk.mode.value !== 'live'"
                  @update:model-value="(val: boolean) => toggleReadReceipts(account, val)"
                />
              </SettingsRow>
            </div>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- QUICK REPLIES (with inline Create/Edit/Delete) -->
      <SettingsPanel value="replies">
        <SettingsHeader
          title="Quick Replies"
          description='Create and manage snippets triggered with "/" in the chat composer.'
        >
          <template #actions>
            <Button
              variant="solid"
              theme="green"
              size="sm"
              icon-left="lucide-plus"
              :label="replyFormOpen ? 'Cancel' : 'New Quick Reply'"
              @click="replyFormOpen ? (replyFormOpen = false) : startReplyEdit()"
            />
          </template>
        </SettingsHeader>
        <SettingsBody>
          <div class="mt-5 space-y-4">
            <div v-if="replyFormOpen" class="space-y-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4">
              <div class="grid gap-3 sm:grid-cols-2">
                <FormControl v-model="replyForm.title" type="text" label="Title" placeholder="e.g. Order Follow-up" />
                <FormControl v-model="replyForm.shortcut" type="text" label="Shortcut (/)" placeholder="followup" />
              </div>
              <FormControl
                v-model="replyForm.body"
                type="textarea"
                label="Message Body"
                :rows="3"
                placeholder="Type the reusable reply message..."
              />
              <div class="flex items-center justify-end gap-2">
                <Button variant="subtle" size="sm" label="Cancel" @click="replyFormOpen = false" />
                <Button
                  variant="solid"
                  theme="green"
                  size="sm"
                  :loading="replySaving"
                  :label="replyForm.name ? 'Save Changes' : 'Create Quick Reply'"
                  @click="submitReply"
                />
              </div>
            </div>

            <TextInput v-model="replySearch" placeholder="Search title, /shortcut, or message...">
              <template #prefix>
                <span class="lucide-search size-3.5 text-ink-gray-4" />
              </template>
            </TextInput>

            <div v-if="repliesLoading" class="py-8 text-center text-xs text-ink-gray-5">
              Loading quick replies…
            </div>
            <EmptyState
              v-else-if="!filteredReplies.length"
              compact
              title="No quick replies found"
              description="Click New Quick Reply above to create your first shortcut."
            />
            <div v-else class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
              <div
                v-for="row in filteredReplies"
                :key="row.name"
                class="flex items-start justify-between gap-4 p-3.5"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <Badge
                      v-if="row.shortcut"
                      theme="green"
                      variant="subtle"
                      :label="'/' + String(row.shortcut).replace(/^\/+/, '')"
                    />
                    <span class="text-sm font-medium text-ink-gray-9">{{ row.title }}</span>
                  </div>
                  <p class="mt-1 line-clamp-2 text-xs text-ink-gray-6">{{ row.body }}</p>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <Button
                    v-if="isManager"
                    variant="ghost"
                    size="sm"
                    label="Edit"
                    @click="startReplyEdit(row)"
                  />
                  <Button
                    v-if="isManager"
                    variant="ghost"
                    size="sm"
                    icon="lucide-trash-2"
                    aria-label="Delete"
                    @click="removeReply(row)"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    :label="copiedShortcut === (row.shortcut ? '/' + row.shortcut : row.title) ? 'Copied' : 'Copy'"
                    @click="copyShortcut(row.body, row.shortcut ? '/' + row.shortcut : row.title)"
                  />
                </div>
              </div>
            </div>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- ROUTING & SLA -->
      <SettingsPanel v-if="isManager" value="routing">
        <SettingsHeader
          title="Routing & SLA"
          description="How conversations are assigned and governed by Meta's 24-hour window."
        />
        <SettingsBody>
          <div class="mt-4 divide-y divide-outline-gray-1">
            <SettingsRow
              title="Manual & team assignment"
              description="Agents can claim unassigned chats or hand off threads from the chat header."
            >
              <Button variant="subtle" size="sm" label="Open Users" @click="activeTab = 'users'" />
            </SettingsRow>
            <SettingsRow
              title="24-hour service window"
              description="Free-form replies and attachments are open for 24h after the customer's last message; outside it, send an approved Meta template."
            >
              <Badge theme="green" variant="subtle" label="Enforced" />
            </SettingsRow>
            <SettingsRow
              title="Role permissions"
              description="WhatsApp User handles assigned & shared chats; WhatsApp Manager manages accounts, campaigns, and automations."
            >
              <Badge theme="gray" variant="subtle" label="RBAC" />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- AUTOMATION & AI (Editable directly inside SettingsDialog) -->
      <SettingsPanel v-if="isManager" value="automation">
        <SettingsHeader
          title="Automation & AI"
          description="Configure chatbot status, business hours, and AI responder for the selected account."
        >
          <template #actions>
            <Button
              variant="subtle"
              size="sm"
              label="Flows & Keywords"
              icon-right="lucide-arrow-up-right"
              @click="openRoute('/automation')"
            />
            <Button
              variant="solid"
              theme="green"
              size="sm"
              :loading="botSaving"
              label="Save"
              @click="submitBot"
            />
          </template>
        </SettingsHeader>
        <SettingsBody>
          <div v-if="botLoading" class="py-8 text-center text-xs text-ink-gray-5">
            Loading automation settings…
          </div>
          <div v-else class="mt-4 space-y-4">
            <div class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2 px-4">
              <SettingsRow
                title="Enable Chatbot Automation"
                description="Automatically process inbound messages with flows, keywords, and AI."
              >
                <Switch v-model="botForm.enabled" />
              </SettingsRow>
              <SettingsRow
                title="Business Hours Only"
                description="Send an out-of-hours message outside configured business hours."
              >
                <Switch v-model="botForm.business_hours_only" />
              </SettingsRow>
              <SettingsRow
                title="Enable AI Responder"
                description="Use an LLM provider when no keyword or flow matches."
              >
                <Switch v-model="botForm.enable_ai" />
              </SettingsRow>
            </div>

            <div class="grid gap-3 sm:grid-cols-2">
              <FormControl
                v-model="botForm.ai_provider"
                type="select"
                label="AI Provider"
                :options="providerOptions"
              />
              <FormControl
                v-model="botForm.ai_model"
                type="text"
                label="AI Model"
                placeholder="e.g. gpt-4o-mini, gemini-2.5-flash"
              />
            </div>

            <FormControl
              v-model="botForm.default_response"
              type="textarea"
              label="Default Fallback Response"
              :rows="2"
              placeholder="Message sent when no keyword/flow matches..."
            />

            <FormControl
              v-if="botForm.business_hours_only"
              v-model="botForm.out_of_hours_message"
              type="textarea"
              label="Out-of-hours Message"
              :rows="2"
              placeholder="We are currently closed. We'll reply during business hours."
            />
          </div>
        </SettingsBody>
      </SettingsPanel>

      <!-- CONNECTED APPS -->
      <SettingsPanel v-if="isManager" value="integrations">
        <SettingsHeader
          title="Connected Apps"
          description="Manage ERPNext sync, automation flows, and webhook delivery logs."
        />
        <SettingsBody>
          <div class="mt-4 divide-y divide-outline-gray-1">
            <SettingsRow
              title="Integrations Hub"
              description="Configure Meta Cloud API, Embedded Signup, and webhook endpoints."
            >
              <Button variant="subtle" size="sm" label="Open" @click="openRoute('/integrations')" />
            </SettingsRow>
            <SettingsRow
              title="External Sites"
              description="Connect external sites via OAuth and manage document notifications."
            >
              <Button variant="subtle" size="sm" label="Configure" @click="openRoute('/external-sites')" />
            </SettingsRow>
            <SettingsRow
              title="Webhook & Delivery Logs"
              description="Inspect inbound webhooks and outbound message status events."
            >
              <Button variant="subtle" size="sm" label="View Logs" @click="openRoute('/integrations/logs')" />
            </SettingsRow>
          </div>
        </SettingsBody>
      </SettingsPanel>
    </SettingsContent>
  </SettingsDialog>
</template>
