<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Badge, Button, call, Dialog, toast } from 'frappe-ui'
import { errorText } from '@/utils/format'
import { deleteQuickReply, getWhatsappSettings, listQuickReplies, saveQuickReply, saveWhatsappSettings, updateWhatsappAccount } from '@/services/catalogApi'
import { isManager, isSiteAdmin, useDesk } from '@/stores/desk'
import { router } from '@/router'

const desk = useDesk()
const loading = ref(true)
const error = ref<string | null>(null)
const replies = ref<any[]>([])
const activeTab = ref<'replies' | 'hours' | 'routing' | 'profile' | 'team' | 'login'>('replies')
const searchQuery = ref('')
const channelFilter = ref('all')
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

const teamMembers = ref<TeamMember[]>([])
const teamLoading = ref(false)
const showAddMemberModal = ref(false)
const showEditMemberModal = ref(false)
const editingMember = ref<TeamMember | null>(null)

// Add Team Member Form
const newMemberName = ref('')
const newMemberEmail = ref('')
const newMemberPassword = ref('')
const newMemberRole = ref<'WhatsApp User' | 'WhatsApp Manager'>('WhatsApp User')
const isSubmittingMember = ref(false)

// Edit Team Member Form
const editRole = ref<'WhatsApp User' | 'WhatsApp Manager'>('WhatsApp User')
const editEnabled = ref(true)
const editNewPassword = ref('')

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
  phone_id: string
  business_id: string
  app_id: string
  access_token: string
} | null>(null)
const accountEditorOpen = ref(false)
const siteSettings = ref({
  default_account: '',
  whatsapp_api_url: '',
  whatsapp_api_version: '',
  webhook_verify_token: '',
  webhook_secret: '',
  has_webhook_secret: false,
  callback_method: 'whatsapp.whatsapp.webhook.handler',
})
const savingSite = ref(false)
const facebookLogin = ref({
  enabled: false,
  app_id: '',
  app_secret: '',
  has_secret: false,
  redirect_uri: '',
  ready: false,
})
const savingFacebook = ref(false)

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

function openIntegrations() {
  void router.push('/integrations')
}

function startReply(row?: any) {
  editingReply.value = row?.name || null
  newTitle.value = row?.title || ''
  newShortcut.value = row?.shortcut || ''
  newBody.value = row?.body || ''
  newChannel.value = row?.whatsapp_account || ''
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
    phone_id: source.phone_id || '',
    business_id: source.business_id || '',
    app_id: source.app_id || '',
    access_token: '',
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
    const result = await listQuickReplies()
    replies.value = result || []
  } catch (caught) {
    if (!isLive) {
      replies.value = fallbackQuickReplies
    } else {
      error.value = errorText(caught)
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
    await updateWhatsappAccount({
      name: accountEditor.value.name,
      status: accountEditor.value.status,
      auto_read_receipts: accountEditor.value.auto_read_receipts ? 1 : 0,
      phone_id: accountEditor.value.phone_id.trim() || undefined,
      business_id: accountEditor.value.business_id.trim() || undefined,
      app_id: accountEditor.value.app_id.trim() || undefined,
      access_token: accountEditor.value.access_token.trim() || undefined,
    })
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

const channelOptions = computed(() => {
  if (desk.mode.value === 'live') {
    return (desk.inbox.value?.accounts || []).map((account) => ({
      value: account.name,
      label: account.account_name || account.name,
    }))
  }
  return [
    { value: 'Sundarban Sales', label: 'Sundarban Sales' },
    { value: 'Sundarban Dispatch', label: 'Sundarban Dispatch' },
  ]
})

const filteredReplies = computed(() => {
  return allReplies.value.filter((row) => {
    if (channelFilter.value !== 'all' && row.whatsapp_account && row.whatsapp_account !== channelFilter.value) {
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
  if (!isLive) {
    teamMembers.value = fallbackTeamMembers
    return
  }
  teamLoading.value = true
  try {
    const res = await call('nudg.desk_api.list_team_members')
    if (Array.isArray(res)) {
      teamMembers.value = res
    } else {
      teamMembers.value = fallbackTeamMembers
    }
  } catch {
    teamMembers.value = fallbackTeamMembers
  } finally {
    teamLoading.value = false
  }
}

const selectedTeamAccount = ref('')

async function handleCreateMember() {
  if (!newMemberName.value.trim() || !newMemberEmail.value.trim() || !newMemberPassword.value.trim()) {
    showToast('Please fill in name, email, and password.', true)
    return
  }
  isSubmittingMember.value = true
  try {
    const acc = selectedTeamAccount.value || desk.inbox.value?.accounts?.[0]?.name || ''
    await call('nudg.desk_api.create_team_member', {
      account: acc,
      full_name: newMemberName.value.trim(),
      email: newMemberEmail.value.trim(),
      password: newMemberPassword.value.trim(),
      role: newMemberRole.value,
    })
    showToast('Team member added successfully!')
    showAddMemberModal.value = false
    newMemberName.value = ''
    newMemberEmail.value = ''
    newMemberPassword.value = ''
    await loadTeamMembers()
  } catch (err: any) {
    showToast(err?.message || 'Failed to add team member', true)
  } finally {
    isSubmittingMember.value = false
  }
}

function openEditMember(member: TeamMember) {
  editingMember.value = member
  editRole.value = member.role
  editEnabled.value = member.enabled
  editNewPassword.value = ''
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
      new_password: editNewPassword.value.trim() || undefined,
    })
    showToast('Team member updated successfully!')
    showEditMemberModal.value = false
    editNewPassword.value = ''
    await loadTeamMembers()
  } catch (err: any) {
    showToast(err?.message || 'Failed to update member', true)
  }
}

async function loadFacebookLogin() {
  if (!isSiteAdmin.value || desk.mode.value !== 'live') return
  try {
    const result = await call<typeof facebookLogin.value>('nudg.desk_api.get_facebook_login_settings')
    facebookLogin.value = {
      enabled: Boolean(result?.enabled),
      app_id: result?.app_id || '',
      app_secret: '',
      has_secret: Boolean(result?.has_secret),
      redirect_uri: result?.redirect_uri || '',
      ready: Boolean(result?.ready),
    }
  } catch (caught) {
    showToast(errorText(caught), true)
  }
}

async function saveFacebookLogin() {
  if (!isSiteAdmin.value || desk.mode.value !== 'live') return
  savingFacebook.value = true
  try {
    const result = await call<typeof facebookLogin.value>('nudg.desk_api.save_facebook_login_settings', {
      app_id: facebookLogin.value.app_id.trim(),
      app_secret: facebookLogin.value.app_secret.trim() || undefined,
      enabled: facebookLogin.value.enabled ? 1 : 0,
    })
    facebookLogin.value = {
      enabled: Boolean(result?.enabled),
      app_id: result?.app_id || facebookLogin.value.app_id,
      app_secret: '',
      has_secret: Boolean(result?.has_secret),
      redirect_uri: result?.redirect_uri || facebookLogin.value.redirect_uri,
      ready: Boolean(result?.ready),
    }
    showToast(facebookLogin.value.enabled ? 'Login with Facebook is on.' : 'Login with Facebook is off.')
  } catch (caught) {
    showToast(errorText(caught), true)
  } finally {
    savingFacebook.value = false
  }
}

async function copyRedirectUri() {
  const uri = facebookLogin.value.redirect_uri
  if (!uri) return
  try {
    await navigator.clipboard.writeText(uri)
    showToast('Redirect URI copied.')
  } catch {
    showToast('Copy the redirect URI from the field.', true)
  }
}

async function loadSiteSettings() {
  if (!isSiteAdmin.value || desk.mode.value !== 'live') return
  try {
    const result = await getWhatsappSettings()
    siteSettings.value = {
      default_account: result?.default_account || '',
      whatsapp_api_url: result?.whatsapp_api_url || '',
      whatsapp_api_version: result?.whatsapp_api_version || '',
      webhook_verify_token: result?.webhook_verify_token || '',
      webhook_secret: '',
      has_webhook_secret: Boolean(result?.has_webhook_secret),
      callback_method: result?.callback_method || 'whatsapp.whatsapp.webhook.handler',
    }
  } catch (caught) {
    showToast(errorText(caught), true)
  }
}

async function saveSiteSettings() {
  if (!isSiteAdmin.value || desk.mode.value !== 'live') return
  savingSite.value = true
  try {
    const saved = await saveWhatsappSettings({
      default_account: siteSettings.value.default_account,
      whatsapp_api_url: siteSettings.value.whatsapp_api_url,
      whatsapp_api_version: siteSettings.value.whatsapp_api_version,
      webhook_verify_token: siteSettings.value.webhook_verify_token,
      webhook_secret: siteSettings.value.webhook_secret,
    })
    siteSettings.value.webhook_secret = ''
    siteSettings.value.has_webhook_secret = Boolean(saved?.has_webhook_secret)
    showToast('WhatsApp settings saved.')
  } catch (caught) {
    showToast(errorText(caught), true)
  } finally {
    savingSite.value = false
  }
}

async function removeReply() {
  if (!editingReply.value) return
  if (!window.confirm(`Delete quick reply “${newTitle.value || editingReply.value}”?`)) return
  if (desk.mode.value === 'live') {
    try {
      await deleteQuickReply(editingReply.value)
    } catch (caught) {
      showToast(errorText(caught), true)
      return
    }
  }
  replies.value = replies.value.filter((row) => row.name !== editingReply.value)
  editingReply.value = null
  showCreateModal.value = false
  showToast('Quick reply deleted.')
}

onMounted(() => {
  desk.load()
  load()
  loadTeamMembers()
  loadSiteSettings()
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-surface-gray-2/60">
    <!-- Main Content Area -->
    <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-8">
      <!-- Header Banner -->
      <div class="flex flex-col gap-4 border-b border-outline-gray-2 pb-6 md:flex-row md:items-center md:justify-between">
        <div>
          <div class="flex items-center gap-2.5">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-[#075E54]/10 text-[#075E54]">
              <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <div>
              <h1 class="text-2xl font-bold tracking-tight text-ink-gray-9">Nudg Settings</h1>
              <p class="text-xs sm:text-sm text-ink-gray-6">
                Configure canned quick replies, routing rules, and WABA profile metadata.
              </p>
            </div>
          </div>
        </div>

        <!-- Top Header Actions -->
        <div class="flex flex-wrap items-center gap-2 sm:gap-3">
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
        </div>
      </div>

      <!-- Settings Navigation Tabs -->
      <div class="mt-6 flex flex-wrap items-center gap-1 border-b border-outline-gray-2 pb-px">
        <button
          type="button"
          @click="activeTab = 'replies'"
          class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all"
          :class="
            activeTab === 'replies'
              ? 'border-[#128C7E] text-[#075E54]'
              : 'border-transparent text-ink-gray-6 hover:text-ink-gray-9'
          "
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <span>Quick Replies</span>
          <span class="rounded-full bg-surface-gray-2 px-2 py-0.5 text-xs font-medium text-ink-gray-7">
            {{ allReplies.length }}
          </span>
        </button>

        <button
          v-if="isManager"
          type="button"
          @click="activeTab = 'routing'"
          class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all"
          :class="
            activeTab === 'routing'
              ? 'border-[#128C7E] text-[#075E54]'
              : 'border-transparent text-ink-gray-6 hover:text-ink-gray-9'
          "
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
          <span>Routing & Assignment</span>
        </button>

        <button
          v-if="isManager"
          type="button"
          @click="activeTab = 'team'; loadTeamMembers()"
          class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all"
          :class="
            activeTab === 'team'
              ? 'border-[#128C7E] text-[#075E54]'
              : 'border-transparent text-ink-gray-6 hover:text-ink-gray-9'
          "
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
          <span>Team &amp; Agents</span>
          <span class="rounded-full bg-surface-gray-2 px-2 py-0.5 text-xs font-medium text-ink-gray-7">
            {{ teamMembers.length }}
          </span>
        </button>

        <button
          v-if="isManager"
          type="button"
          @click="activeTab = 'profile'"
          class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all"
          :class="
            activeTab === 'profile'
              ? 'border-[#128C7E] text-[#075E54]'
              : 'border-transparent text-ink-gray-6 hover:text-ink-gray-9'
          "
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
          <span>WABA Profile</span>
        </button>

        <button
          v-if="isSiteAdmin"
          type="button"
          @click="activeTab = 'login'; loadFacebookLogin()"
          class="flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs sm:text-sm font-semibold transition-all"
          :class="
            activeTab === 'login'
              ? 'border-[#128C7E] text-[#075E54]'
              : 'border-transparent text-ink-gray-6 hover:text-ink-gray-9'
          "
        >
          <span>Facebook login</span>
        </button>
      </div>

      <!-- TAB 1: QUICK REPLIES -->
      <div v-if="activeTab === 'replies'" class="mt-6 space-y-6">
        <!-- KPI Metrics -->
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div class="rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs">
            <span class="text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Configured Shortcuts</span>
            <div class="mt-2 flex items-baseline gap-2">
              <span class="text-2xl font-bold text-ink-gray-9">{{ allReplies.length }}</span>
              <span class="text-xs text-ink-gray-5">active templates</span>
            </div>
            <p class="mt-1 text-xs text-ink-gray-6">Triggerable via "/" in composer</p>
          </div>

          <div class="rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs">
            <span class="text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Most Used Shortcut</span>
            <div class="mt-2 flex items-baseline gap-2">
              <span class="font-mono text-lg font-bold text-[#075E54]">/{{ mostUsedReply?.shortcut || 'greet' }}</span>
              <span class="text-xs text-ink-gray-5">({{ mostUsedReply?.usage_count || 0 }} times)</span>
            </div>
            <p class="mt-1 text-xs text-ink-gray-6">{{ mostUsedReply?.title || 'Welcome Greeting' }}</p>
          </div>

          <div class="rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs">
            <span class="text-xs font-medium text-ink-gray-6 uppercase tracking-wider">Fast Dispatch Mode</span>
            <div class="mt-2 flex items-baseline gap-2">
              <span class="text-lg font-bold text-ink-gray-9">Freeform & Variables</span>
            </div>
            <p class="mt-1 text-xs text-ink-gray-6">Single-click insertion in Inbox</p>
          </div>
        </div>

        <!-- Filter & Search Toolbar -->
        <div class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-white p-4 shadow-2xs sm:flex-row sm:items-center sm:justify-between">
          <div class="relative w-full sm:w-72">
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search title, /shortcut, body..."
              class="h-8.5 w-full rounded-lg border border-outline-gray-2 bg-surface-gray-2/50 pl-8 pr-3 text-xs text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            />
            <svg class="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-ink-gray-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>

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

        <!-- Quick Replies Grid -->
        <div v-if="filteredReplies.length > 0" class="grid gap-4 sm:grid-cols-2">
          <article
            v-for="row in filteredReplies"
            :key="row.name"
            class="flex flex-col justify-between rounded-xl border border-outline-gray-2 bg-white p-5 shadow-2xs hover:border-[#128C7E]/40 hover:shadow-xs transition-all"
          >
            <div>
              <div class="flex items-start justify-between gap-3">
                <div class="flex items-center gap-2">
                  <span
                    v-if="row.shortcut"
                    class="rounded-md bg-[#075E54]/10 px-2 py-0.5 font-mono text-xs font-bold text-[#075E54]"
                  >
                    /{{ row.shortcut }}
                  </span>
                  <h3 class="text-sm font-semibold text-ink-gray-9">{{ row.title }}</h3>
                </div>

                <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                  {{ row.status || 'Active' }}
                </span>
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

              <div class="flex items-center gap-2">
                <button
                  v-if="isManager"
                  type="button"
                  class="text-xs font-semibold text-ink-gray-7 hover:text-[#075E54]"
                  @click="startReply(row)"
                >
                  Edit
                </button>
                <button
                  type="button"
                  @click="copyText(row.body, row.shortcut ? '/' + row.shortcut : row.title)"
                  class="text-xs font-semibold text-[#075E54] hover:underline"
                >
                  {{ copiedShortcut === (row.shortcut ? '/' + row.shortcut : row.title) ? 'Copied!' : 'Copy Text' }}
                </button>
              </div>
            </div>
          </article>
        </div>

        <div
          v-else
          class="flex flex-col items-center justify-center rounded-xl border border-dashed border-outline-gray-2 bg-white p-12 text-center"
        >
          <div class="flex h-12 w-12 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-5">
            <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <h3 class="mt-3 text-sm font-semibold text-ink-gray-9">No Quick Replies Found</h3>
          <p class="mt-1 text-xs text-ink-gray-5">No replies match the current filter or search criteria.</p>
          <button
            type="button"
            @click="searchQuery = ''; channelFilter = 'all'"
            class="mt-4 rounded-lg bg-[#075E54] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#128C7E]"
          >
            Reset Filters
          </button>
        </div>
      </div>

      <!-- TAB 2: ROUTING & AUTO-ASSIGNMENT -->
      <div v-else-if="activeTab === 'routing'" class="mt-6 space-y-6">
        <div class="grid gap-6 sm:grid-cols-3">
          <!-- Card 1 -->
          <div class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-2xs">
            <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600 mb-3">
              <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </div>
            <h3 class="text-sm font-semibold text-ink-gray-9">Frappe Assignment Rules</h3>
            <p class="mt-1 text-xs text-ink-gray-6 leading-relaxed">
              Assign conversations from the inbox, and add agents from the Team tab.
            </p>
            <button
              v-if="isManager"
              type="button"
              class="mt-3 text-xs font-semibold text-[#075E54] hover:underline"
              @click="activeTab = 'team'; loadTeamMembers()"
            >
              Open team
            </button>
          </div>

          <!-- Card 2 -->
          <div class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-2xs">
            <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 mb-3">
              <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <h3 class="text-sm font-semibold text-ink-gray-9">Agent Role & Permissions</h3>
            <p class="mt-1 text-xs text-ink-gray-6 leading-relaxed">
              Users with the <code class="rounded bg-surface-gray-2 px-1 text-[11px]">WhatsApp User</code> role can chat with assigned leads and view shared inboxes. Administrators require <code class="rounded bg-surface-gray-2 px-1 text-[11px]">System Manager</code>.
            </p>
          </div>

          <!-- Card 3 -->
          <div class="rounded-xl border border-outline-gray-2 bg-white p-5 shadow-2xs">
            <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-purple-50 text-purple-600 mb-3">
              <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 class="text-sm font-semibold text-ink-gray-9">24h SLA Session Window</h3>
            <p class="mt-1 text-xs text-ink-gray-6 leading-relaxed">
              Meta enforces a 24-hour service window per conversation. Inbound replies automatically re-open the freeform window for support agents.
            </p>
          </div>
        </div>
      </div>

      <div v-else-if="activeTab === 'profile'" class="mt-6 space-y-6">
        <template v-if="desk.mode.value === 'live'">
          <div
            v-if="!(desk.inbox.value?.accounts || []).length"
            class="rounded-xl border border-outline-gray-2 bg-white p-6 text-sm text-ink-gray-6"
          >
            No WhatsApp account is connected yet. Add one from Integrations.
          </div>
          <div
            v-for="account in desk.inbox.value?.accounts || []"
            :key="account.name"
            class="rounded-xl border border-outline-gray-2 bg-white p-6 shadow-2xs"
          >
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 class="text-lg font-bold text-ink-gray-9">{{ account.account_name || account.name }}</h2>
                <p class="mt-1 text-xs text-ink-gray-5">{{ account.name }} · {{ account.status }}</p>
              </div>
              <button
                v-if="isManager"
                type="button"
                class="rounded-lg border border-outline-gray-2 px-3.5 py-2 text-xs font-semibold text-ink-gray-8 hover:bg-surface-gray-2"
                @click="startAccountEdit(account)"
              >
                Edit
              </button>
            </div>
          </div>
          <div v-if="isSiteAdmin" class="rounded-xl border border-outline-gray-2 bg-white p-6 shadow-2xs">
            <h2 class="text-lg font-bold text-ink-gray-9">WhatsApp settings</h2>
            <p class="mt-1 text-xs text-ink-gray-5">
              Site-wide. Only an Administrator or System Manager can see this. Callback: {{ siteSettings.callback_method }}
            </p>
            <p class="mt-2 text-xs leading-relaxed text-ink-gray-6">
              Optional. Leave this empty on a multi-client site. Connecting or removing a number does not fill it.
              It is used only when a webhook or send does not name a number and that number cannot be matched by phone id.
              People still message only from numbers they are allowed to use.
            </p>
            <div class="mt-4 grid gap-3 sm:grid-cols-2 text-xs">
              <label class="block font-semibold text-ink-gray-7">
                Default account
                <select v-model="siteSettings.default_account" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 font-normal">
                  <option value="">None</option>
                  <option v-for="account in desk.inbox.value?.accounts || []" :key="account.name" :value="account.name">
                    {{ account.account_name || account.name }}
                  </option>
                </select>
              </label>
              <label class="block font-semibold text-ink-gray-7">
                API version
                <input v-model="siteSettings.whatsapp_api_version" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 font-normal" placeholder="v23.0" />
              </label>
              <label class="block font-semibold text-ink-gray-7 sm:col-span-2">
                API URL
                <input v-model="siteSettings.whatsapp_api_url" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 font-normal" placeholder="https://graph.facebook.com" />
              </label>
              <label class="block font-semibold text-ink-gray-7">
                Webhook verify token
                <input v-model="siteSettings.webhook_verify_token" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 font-normal" />
              </label>
              <label class="block font-semibold text-ink-gray-7">
                Webhook secret
                <input
                  v-model="siteSettings.webhook_secret"
                  type="password"
                  class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 font-normal"
                  :placeholder="siteSettings.has_webhook_secret ? 'Saved. Type a new secret to replace it.' : 'App secret from Meta'"
                />
              </label>
            </div>
            <div class="mt-4 flex justify-end">
              <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" label="Save settings" :loading="savingSite" @click="saveSiteSettings" />
            </div>
          </div>
        </template>
        <div v-else class="rounded-xl border border-outline-gray-2 bg-white p-6 shadow-2xs">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between border-b border-outline-gray-2 pb-5">
            <div class="flex items-start gap-4">
              <div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-[#075E54] text-white shadow-sm font-bold text-xl">
                SS
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <h2 class="text-lg font-bold text-ink-gray-9">Sundarban Spices & Agri Corp</h2>
                  <span class="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                    <svg class="h-3.5 w-3.5 text-emerald-600" fill="currentColor" viewBox="0 0 20 20">
                      <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                    </svg>
                    Meta Verified Business
                  </span>
                </div>
                <p class="mt-1 text-xs text-ink-gray-5">Official WhatsApp Business Account (WABA ID: 9920148123901)</p>
              </div>
            </div>

            <button
              v-if="isManager"
              type="button"
              class="rounded-lg border border-outline-gray-2 px-3.5 py-2 text-xs font-semibold text-ink-gray-8 hover:bg-surface-gray-2 transition-all"
              @click="openIntegrations"
            >
              Connect a number
            </button>
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
        </div>
      </div>

      <!-- TAB 5: TEAM & AGENTS -->
      <div v-else-if="activeTab === 'login'" class="mt-6 space-y-6">
        <div class="rounded-xl border border-outline-gray-2 bg-white p-6 shadow-2xs">
          <h2 class="text-lg font-bold text-ink-gray-9">Login with Facebook</h2>
          <p class="mt-1 text-sm text-ink-gray-6">
            People use this to sign in to Nudg. A new person gets the WhatsApp User role and opens Nudg.
            Google sign-in is not available yet.
          </p>
          <p class="mt-2 text-sm text-ink-gray-6">
            Connecting a WhatsApp number stays on Integrations. That Facebook window is Embedded Signup, not this login.
          </p>
          <div v-if="desk.mode.value !== 'live'" class="mt-4 text-sm text-ink-gray-6">
            Open Nudg on the site to save the Facebook App ID and app secret.
          </div>
          <div v-else class="mt-4 max-w-xl space-y-4">
            <label class="flex items-center gap-2 text-sm font-medium text-ink-gray-8">
              <input v-model="facebookLogin.enabled" type="checkbox" class="rounded border-outline-gray-2" />
              Enable Login with Facebook
            </label>
            <label class="block text-sm font-medium text-ink-gray-8">
              Facebook App ID
              <input v-model="facebookLogin.app_id" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 font-normal" />
            </label>
            <label class="block text-sm font-medium text-ink-gray-8">
              App secret
              <input
                v-model="facebookLogin.app_secret"
                type="password"
                autocomplete="new-password"
                class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2 font-normal"
                :placeholder="facebookLogin.has_secret ? 'Saved. Type a new secret to replace it.' : 'Meta app secret'"
              />
            </label>
            <label class="block text-sm font-medium text-ink-gray-8">
              Redirect URI
              <input
                :value="facebookLogin.redirect_uri"
                readonly
                class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 font-normal text-ink-gray-7"
              />
            </label>
            <p class="text-xs leading-relaxed text-ink-gray-6">
              In the Meta app, add Facebook Login and paste this redirect URI. The App ID can be the same one used for Embedded Signup.
            </p>
            <div class="flex flex-wrap gap-2">
              <Button
                variant="solid"
                class="bg-[#075E54] text-white hover:bg-[#128C7E]"
                :loading="savingFacebook"
                label="Save"
                @click="saveFacebookLogin"
              />
              <Button variant="subtle" label="Copy redirect URI" @click="copyRedirectUri" />
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="activeTab === 'team'" class="mt-6 space-y-6">
        <div class="rounded-xl border border-outline-gray-2 bg-white p-6 shadow-2xs">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-outline-gray-2 pb-5">
            <div>
              <h2 class="text-lg font-bold text-ink-gray-9">Team Members &amp; Agents</h2>
              <p class="mt-1 text-xs text-ink-gray-6">
                Manage agent accounts, scoped roles, and WhatsApp permissions directly in Nudg without opening Desk.
              </p>
            </div>
            <Button
              variant="solid"
              class="bg-[#075E54] text-white hover:bg-[#128C7E] shrink-0 font-medium"
              label="Add Team Member"
              icon-left="lucide-user-plus"
              @click="showAddMemberModal = true"
            />
          </div>

          <!-- Members Table -->
          <div class="mt-4 overflow-x-auto">
            <table class="min-w-full divide-y divide-outline-gray-2 text-xs">
              <thead>
                <tr class="text-left text-ink-gray-5">
                  <th class="py-3 pr-4 font-semibold uppercase tracking-wider">Agent</th>
                  <th class="py-3 px-4 font-semibold uppercase tracking-wider">Role</th>
                  <th class="py-3 px-4 font-semibold uppercase tracking-wider">WhatsApp Account</th>
                  <th class="py-3 px-4 font-semibold uppercase tracking-wider">Status</th>
                  <th class="py-3 pl-4 text-right font-semibold uppercase tracking-wider">Action</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-outline-gray-2">
                <tr v-for="member in teamMembers" :key="member.email" class="hover:bg-surface-gray-1">
                  <td class="py-3 pr-4">
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
                  <td class="py-3 px-4">
                    <span
                      class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold"
                      :class="member.role === 'WhatsApp Manager' ? 'bg-purple-50 text-purple-700 border border-purple-200' : 'bg-blue-50 text-blue-700 border border-blue-200'"
                    >
                      {{ member.role }}
                    </span>
                  </td>
                  <td class="py-3 px-4 text-ink-gray-7 font-medium">
                    {{ member.account || 'All Permitted' }}
                  </td>
                  <td class="py-3 px-4">
                    <span
                      class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
                      :class="member.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'"
                    >
                      <span class="h-1.5 w-1.5 rounded-full" :class="member.enabled ? 'bg-emerald-500' : 'bg-red-500'"></span>
                      {{ member.enabled ? 'Active' : 'Disabled' }}
                    </span>
                  </td>
                  <td class="py-3 pl-4 text-right">
                    <button
                      v-if="!member.is_owner"
                      type="button"
                      @click="openEditMember(member)"
                      class="text-[#075E54] hover:underline font-semibold"
                    >
                      Edit
                    </button>
                    <span v-else class="text-ink-gray-4 text-[11px]">Owner</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

    <!-- MODAL: Add Team Member -->
    <Dialog
      v-model="showAddMemberModal"
      title="Add Team Member"
      size="xl"
    >
      <div class="space-y-4 py-1 text-xs">
        <p class="text-xs text-ink-gray-6 -mt-2">
          Create a team member account and automatically grant them WhatsApp access.
        </p>

        <div>
          <label class="block font-semibold text-ink-gray-7">Full Name <span class="text-red-500">*</span></label>
          <input
            v-model="newMemberName"
            type="text"
            class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            placeholder="e.g. John Doe"
            required
          />
        </div>

        <div>
          <label class="block font-semibold text-ink-gray-7">Email Address <span class="text-red-500">*</span></label>
          <input
            v-model="newMemberEmail"
            type="email"
            class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            placeholder="agent@example.com"
            required
          />
        </div>

        <div>
          <label class="block font-semibold text-ink-gray-7">Password <span class="text-red-500">*</span></label>
          <input
            v-model="newMemberPassword"
            type="password"
            class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            placeholder="Min 6 characters"
            required
          />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block font-semibold text-ink-gray-7">Role</label>
            <select
              v-model="newMemberRole"
              class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            >
              <option value="WhatsApp User">WhatsApp User (Agent)</option>
              <option value="WhatsApp Manager">WhatsApp Manager (Admin)</option>
            </select>
          </div>

          <div>
            <label class="block font-semibold text-ink-gray-7">Assign WhatsApp Account</label>
            <select
              v-model="selectedTeamAccount"
              class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            >
              <option v-for="acc in desk.inbox.value?.accounts || []" :key="acc.name" :value="acc.name">
                {{ acc.account_name || acc.name }}
              </option>
            </select>
          </div>
        </div>
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
            label="Create Team Member"
            @click="handleCreateMember"
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
      <div v-if="editingMember" class="space-y-4 py-1 text-xs">
        <div>
          <label class="block font-semibold text-ink-gray-7">Role</label>
          <select
            v-model="editRole"
            class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
          >
            <option value="WhatsApp User">WhatsApp User</option>
            <option value="WhatsApp Manager">WhatsApp Manager</option>
          </select>
        </div>

        <div>
          <label class="block font-semibold text-ink-gray-7">Reset Password (Optional)</label>
          <input
            v-model="editNewPassword"
            type="password"
            class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            placeholder="Leave empty to keep current password"
          />
        </div>

        <div class="pt-2">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input
              v-model="editEnabled"
              type="checkbox"
              class="rounded border-outline-gray-3 text-[#075E54] focus:ring-[#128C7E]"
            />
            <span class="text-xs font-semibold text-ink-gray-8">Account Enabled</span>
          </label>
        </div>
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

    <Dialog v-model="accountEditorOpen" :title="accountEditor ? 'Edit ' + accountEditor.account_name : 'WhatsApp account'">
      <div v-if="accountEditor" class="space-y-4 py-1 text-xs">
        <p class="text-ink-gray-6">A new number is connected from Integrations. Update the credentials Meta issued for this number. Leave the token blank to keep the current one.</p>
        <label class="block font-semibold text-ink-gray-7">
          Phone number ID
          <input v-model="accountEditor.phone_id" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" />
        </label>
        <label class="block font-semibold text-ink-gray-7">
          Business ID
          <input v-model="accountEditor.business_id" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" />
        </label>
        <label class="block font-semibold text-ink-gray-7">
          App ID
          <input v-model="accountEditor.app_id" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" />
        </label>
        <label class="block font-semibold text-ink-gray-7">
          Access token
          <input v-model="accountEditor.access_token" type="password" class="mt-1 block w-full rounded-lg border border-outline-gray-2 px-3 py-2" placeholder="Leave blank to keep the current token" />
        </label>
        <div>
          <label class="block font-semibold text-ink-gray-7">Status</label>
          <select
            v-model="accountEditor.status"
            class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9"
          >
            <option value="Active">Active</option>
            <option value="Inactive">Inactive</option>
          </select>
        </div>
        <label class="flex items-center gap-2 text-ink-gray-8">
          <input v-model="accountEditor.auto_read_receipts" type="checkbox" />
          Send read receipts
        </label>
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
      <div class="space-y-4 py-1 text-xs">
        <p class="text-xs text-ink-gray-6 -mt-2">
          Create a keyboard shortcut for fast customer replies in conversation threads
        </p>

        <div>
          <label class="block font-semibold text-ink-gray-7">Title</label>
          <input
            v-model="newTitle"
            type="text"
            class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            placeholder="e.g. Return Policy Notice"
          />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block font-semibold text-ink-gray-7">Keyboard Shortcut</label>
            <div class="relative mt-1">
              <span class="pointer-events-none absolute left-3 top-2 text-ink-gray-4 font-mono">/</span>
              <input
                v-model="newShortcut"
                type="text"
                class="block w-full rounded-lg border border-outline-gray-2 bg-white pl-6 pr-3 py-2 font-mono text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
                placeholder="return"
              />
            </div>
          </div>

          <div>
            <label class="block font-semibold text-ink-gray-7">Status</label>
            <select
              v-model="replyStatus"
              class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9"
            >
              <option value="Active">Active</option>
              <option value="Inactive">Inactive</option>
            </select>
          </div>

          <div>
            <label class="block font-semibold text-ink-gray-7">Channel</label>
            <select
              v-model="newChannel"
              class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            >
              <option value="">Global (All Channels)</option>
              <option v-for="option in channelOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </div>
        </div>

        <div>
          <label class="block font-semibold text-ink-gray-7">Message Body</label>
          <textarea
            v-model="newBody"
            rows="4"
            class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white p-2.5 text-xs text-ink-gray-9 focus:border-[#128C7E] focus:outline-none focus:ring-1 focus:ring-[#128C7E]"
            placeholder="Type message text to be inserted in the conversation composer..."
          ></textarea>
        </div>
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
    </div>
  </div>
</template>
