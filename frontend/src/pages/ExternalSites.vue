<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Alert, Badge, Button, Password, TextInput, call, Dialog, toast } from 'frappe-ui'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { errorText } from '@/utils/format'
import { accountArg, labelForAccount } from '@/utils/accountSelection'
import { userFacingError } from '@/utils/errors'
import { useDesk } from '@/stores/desk'

const desk = useDesk()
const route = useRoute()
const router = useRouter()
const live = computed(() => Boolean(window.csrf_token))

const loading = ref(true)
const error = ref<string | null>(null)
const busyAction = ref<string | null>(null)
function isBusy(actionKey: string) {
  return busyAction.value === actionKey
}
const sites = ref<any[]>([])
const accounts = computed(() => desk.inbox.value?.accounts || [])

const currentAccount = computed(() => accountArg(desk.account.value) || '')
const currentAccountLabel = computed(() => labelForAccount(accounts.value, currentAccount.value))

// Filter sites by currently selected WhatsApp account (or all if none selected)
const accountSites = computed(() => {
  const account = currentAccount.value
  if (!account) return sites.value
  return sites.value.filter((site) => !site.whatsapp_account || site.whatsapp_account === account)
})

// Dialog state for Connect / Edit
const siteDialogOpen = ref(false)
const isEditing = ref(false)
const editingAccountName = ref('')
const siteForm = ref({
  site_name: '',
  site_url: '',
  client_id: '',
  client_secret: '',
})
const preparedRedirectUri = ref('')

// Verification dialog state
const verifyOpen = ref(false)
const verifyOk = ref(false)
const verifyReason = ref('')
const verifyChecks = ref<{ name: string; ok: boolean; detail: string }[]>([])
const lastVerifiedSite = ref<any>(null)

function cleanUrl(value: string | undefined) {
  return (value || '').trim().replace(/\/+$/, '')
}

function statusTheme(status: string): 'green' | 'red' | 'amber' | 'gray' {
  if (status === 'Connected') return 'green'
  if (status === 'Error') return 'red'
  if (status === 'Pending') return 'amber'
  return 'gray'
}

// Generates the JSON document payload for Frappe's native clipboard copy-paste feature in Desk (Ctrl + V)
const deskClipboardPayload = computed(() => {
  const uri = preparedRedirectUri.value || ''
  return JSON.stringify({
    doctype: 'OAuth Client',
    app_name: 'Nudg',
    default_redirect_uri: uri,
    redirect_uris: uri,
    scopes: 'all openid',
    grant_type: 'Authorization Code',
    response_type: 'Code',
    skip_authorization: 1,
    token_endpoint_auth_method: 'Client Secret Basic',
  })
})

async function copyDeskPayload() {
  if (!deskClipboardPayload.value) return
  await copyToClipboard(deskClipboardPayload.value, 'Setup data')
  toast.success('Copied! Open your external site Desk and press Ctrl + V to create the OAuth Client.')
}

function openCreateModal() {
  isEditing.value = false
  editingAccountName.value = currentAccount.value || ''
  siteForm.value = {
    site_name: '',
    site_url: '',
    client_id: '',
    client_secret: '',
  }
  preparedRedirectUri.value = ''
  siteDialogOpen.value = true
}

function openEditModal(site: any) {
  isEditing.value = true
  editingAccountName.value = site.whatsapp_account || site.name || currentAccount.value || ''
  siteForm.value = {
    site_name: site.site_name || '',
    site_url: site.site_url || '',
    client_id: site.client_id || '',
    client_secret: '',
  }
  preparedRedirectUri.value = site.redirect_uri || ''
  siteDialogOpen.value = true
}

async function load() {
  if (!live.value) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = null
  try {
    sites.value = (await call<any[]>('nudg.integrations.erpnext.api.list_sites')) || []
  } catch (err) {
    error.value = errorText(err)
  } finally {
    loading.value = false
  }
}

async function saveOAuthApp(actionKey = 'modal:save') {
  const account = editingAccountName.value || currentAccount.value || ''
  if (!siteForm.value.site_name.trim() || !siteForm.value.site_url.trim()) {
    toast.error('Site name and Site URL are required.')
    return null
  }
  busyAction.value = actionKey
  try {
    const result = await call<any>('nudg.integrations.erpnext.api.prepare_site_oauth', {
      site_name: siteForm.value.site_name,
      site_url: siteForm.value.site_url,
      whatsapp_account: account || undefined,
      client_id: siteForm.value.client_id || undefined,
      client_secret: siteForm.value.client_secret || undefined,
    })
    preparedRedirectUri.value = result?.redirect_uri || ''
    siteForm.value.client_secret = ''
    await load()
    toast.success('Site configuration saved.')
    return result
  } catch (err) {
    toast.error(errorText(err))
    return null
  } finally {
    busyAction.value = null
  }
}

async function handleAuthorizeFromModal() {
  busyAction.value = 'modal:authorize'
  try {
    const saved = await saveOAuthApp('modal:authorize')
    if (!saved) return
    if (!saved.has_client_credentials && !siteForm.value.client_id.trim()) {
      toast.error('Please enter the OAuth Client ID and Client Secret from your external site.')
      return
    }
    siteDialogOpen.value = false
    await authorizeSite(saved, false, 'modal:authorize')
  } finally {
    busyAction.value = null
  }
}

async function authorizeSite(site: any, newTab = false, actionKey?: string) {
  const key = actionKey || `authorize:${site.name}`
  busyAction.value = key
  try {
    const successUri = `${window.location.pathname}?authorized=1&site=${encodeURIComponent(site.site_name || site.name)}`
    const res = await call<any>('nudg.integrations.erpnext.api.authorize_site', {
      site: site.name,
      success_uri: successUri,
    })
    if (res?.authorization_url) {
      if (newTab) {
        window.open(res.authorization_url, '_blank', 'noopener,noreferrer')
        toast.info('Opened external site authorization. Approve access, then click Verify here.')
      } else {
        window.location.href = res.authorization_url
      }
      return
    }
    toast.error('Could not generate the OAuth authorization URL.')
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busyAction.value = null
  }
}

async function verifySite(siteName: string) {
  busyAction.value = `verify:${siteName}`
  try {
    const result = await call<any>('nudg.integrations.erpnext.api.verify_site', { site: siteName })
    await load()
    lastVerifiedSite.value = sites.value.find((s: any) => s.site_name === siteName || s.name === siteName) || null
    verifyOk.value = Boolean(result?.ok) && result?.status !== 'Error'
    verifyChecks.value = Array.isArray(result?.checks) ? result.checks : []
    if (verifyOk.value) {
      const user = result?.remote_user ? ` Signed in as ${result.remote_user}.` : ''
      verifyReason.value = `Site verified successfully.${user} Required DocTypes are present and WhatsApp message sync is active.`
    } else {
      verifyReason.value = result?.reason || result?.last_error || 'The external site could not be verified.'
    }
    verifyOpen.value = true
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busyAction.value = null
  }
}

function handlePullFromVerify() {
  verifyOpen.value = false
  if (lastVerifiedSite.value) {
    openPullModal(lastVerifiedSite.value)
  }
}

async function copyToClipboard(text: string, label = 'Copied') {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    toast.success(`${label} copied to clipboard!`)
  } catch {
    toast.error(`Could not copy ${label}.`)
  }
}

async function toggleSite(site: any) {
  busyAction.value = `toggle:${site.name}`
  try {
    await call('nudg.integrations.erpnext.api.set_site_enabled', {
      site: site.name,
      enabled: site.status === 'Connected' ? 0 : 1,
    })
    await load()
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busyAction.value = null
  }
}

// Pull WhatsApp Accounts from Connected External Site
const pullDialogOpen = ref(false)
const pullTargetSite = ref<any>(null)
const remoteAccounts = ref<any[]>([])
const selectedRemoteAccounts = ref<string[]>([])
const loadingRemoteAccounts = ref(false)

async function openPullModal(site: any) {
  pullTargetSite.value = site
  pullDialogOpen.value = true
  remoteAccounts.value = []
  selectedRemoteAccounts.value = []
  loadingRemoteAccounts.value = true
  try {
    const res = await call<any[]>('nudg.integrations.erpnext.api.get_remote_wa_accounts', {
      site: site.site_name || site.name,
    })
    remoteAccounts.value = Array.isArray(res) ? res : []
    selectedRemoteAccounts.value = remoteAccounts.value.map((a: any) => a.account_name || a.name)
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    loadingRemoteAccounts.value = false
  }
}

async function confirmPullAccounts() {
  if (!pullTargetSite.value || !selectedRemoteAccounts.value.length) {
    toast.error('Please select at least one WhatsApp account to pull.')
    return
  }
  const accountsToPull = remoteAccounts.value.filter((a: any) =>
    selectedRemoteAccounts.value.includes(a.account_name || a.name)
  )
  busyAction.value = 'pull:confirm'
  try {
    const res = await call<any>('nudg.integrations.erpnext.api.pull_remote_wa_accounts', {
      site: pullTargetSite.value.site_name || pullTargetSite.value.name,
      selected_accounts: accountsToPull,
    })
    if (res?.ok) {
      const msg = `Successfully pulled ${res.created || 0} new account(s), updated ${res.updated || 0} existing.`
      toast.success(msg)
      pullDialogOpen.value = false
      await load()
      window.dispatchEvent(new CustomEvent('nudg:accounts-updated'))
    }
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busyAction.value = null
  }
}

function toggleSelectAccount(accName: string) {
  const idx = selectedRemoteAccounts.value.indexOf(accName)
  if (idx > -1) {
    selectedRemoteAccounts.value.splice(idx, 1)
  } else {
    selectedRemoteAccounts.value.push(accName)
  }
}

function selectAllAccounts() {
  if (selectedRemoteAccounts.value.length === remoteAccounts.value.length) {
    selectedRemoteAccounts.value = []
  } else {
    selectedRemoteAccounts.value = remoteAccounts.value.map((a: any) => a.account_name || a.name)
  }
}

onMounted(async () => {
  await load()
  const params = new URLSearchParams(window.location.search)
  if (params.get('authorized') === '1') {
    const siteName = params.get('site')
    window.history.replaceState({}, '', window.location.pathname)
    if (siteName) {
      await verifySite(siteName)
      const target = sites.value.find((s: any) => s.site_name === siteName || s.name === siteName)
      if (target && target.status === 'Connected') {
        await openPullModal(target)
      }
    }
  }
})
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-surface-base">
    <div class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex max-w-4xl flex-col gap-6">

        <!-- Top Header Banner -->
        <header class="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-5 shadow-sm">
          <div>
            <div class="flex items-center gap-2">
              <h1 class="text-lg font-semibold text-ink-gray-9">External Sites</h1>
              <Badge variant="subtle" theme="gray" label="OAuth 2.0" />
            </div>
            <p class="mt-1 text-sm text-ink-gray-6">
              Connect external Frappe/ERPNext sites via OAuth. Chats and contacts sync seamlessly, while native Append Actions link messages to CRM records.
            </p>
          </div>
          <Button
            variant="solid"
            theme="green"
            icon-left="lucide-plus"
            label="Connect Site"
            @click="openCreateModal"
          />
        </header>

        <!-- Loading / Error States -->
        <LoadingState v-if="loading" />
        <ErrorState v-else-if="error" :message="error" allow-retry @retry="load" />

        <!-- Empty State -->
        <EmptyState
          v-else-if="!accountSites.length"
          title="No external sites connected"
          description="Click 'Connect Site' above to link an external ERPNext or Frappe instance using OAuth 2.0."
        >
          <template #actions>
            <Button variant="solid" theme="green" label="Connect Site" @click="openCreateModal" />
          </template>
        </EmptyState>

        <!-- Connected Sites Cards List -->
        <div v-else class="space-y-4">
          <div
            v-for="site in accountSites"
            :key="site.name"
            class="rounded-xl border border-outline-gray-2 bg-surface-base p-5 shadow-sm transition-all hover:border-outline-gray-3"
          >
            <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              
              <!-- Site Info -->
              <div class="space-y-1.5 min-w-0">
                <div class="flex flex-wrap items-center gap-2.5">
                  <h2 class="text-base font-semibold text-ink-gray-9">{{ site.site_name }}</h2>
                  <Badge
                    :theme="statusTheme(site.status)"
                    variant="subtle"
                    :label="site.status || 'Pending'"
                  />
                  <span class="text-xs text-ink-gray-4">·</span>
                  <span class="text-xs font-mono text-ink-gray-6">{{ site.auth_mode === 'oauth' ? 'OAuth 2.0' : 'API Key' }}</span>
                </div>

                <div class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6">
                  <a :href="site.site_url" target="_blank" rel="noopener noreferrer" class="hover:underline flex items-center gap-1 font-mono text-xs text-ink-gray-7">
                    {{ cleanUrl(site.site_url) }}
                    <span class="text-[10px] text-ink-gray-4">↗</span>
                  </a>
                  <span v-if="site.remote_user" class="text-xs text-ink-gray-5">
                    · Signed in as <strong class="text-ink-gray-8">{{ site.remote_user }}</strong>
                  </span>
                </div>

                <!-- Redirect URI Row (if OAuth enabled) -->
                <div v-if="site.redirect_uri" class="mt-2.5 flex items-center gap-2 rounded-md bg-surface-gray-2 px-2.5 py-1.5 text-xs text-ink-gray-7 max-w-xl">
                  <span class="font-medium shrink-0 text-ink-gray-5">Redirect URI:</span>
                  <span class="truncate font-mono text-[11px] text-ink-gray-8">{{ site.redirect_uri }}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon="lucide-copy"
                    class="shrink-0 ml-auto h-6 px-1.5 text-xs"
                    label="Copy"
                    @click="copyToClipboard(site.redirect_uri, 'Redirect URI')"
                  />
                </div>

                <!-- Last Error Alert (if any) -->
                <Alert
                  v-if="site.last_error"
                  class="mt-3"
                  theme="red"
                  title="Connection issue detected"
                  :description="userFacingError(site.last_error, 'Could not authenticate with this site.')"
                  :primary-action="{ label: 'Refresh', onClick: () => load() }"
                />
              </div>

              <!-- Action Buttons -->
              <div class="flex shrink-0 flex-wrap items-center gap-2 pt-1 sm:pt-0">
                <Button
                  variant="subtle"
                  size="sm"
                  label="Edit"
                  :disabled="Boolean(busyAction)"
                  @click="openEditModal(site)"
                />
                <Button
                  v-if="site.auth_mode === 'oauth'"
                  variant="subtle"
                  size="sm"
                  :loading="isBusy('verify:' + site.name)"
                  :disabled="Boolean(busyAction && !isBusy('verify:' + site.name))"
                  label="Verify"
                  @click="verifySite(site.name)"
                />
                <Button
                  v-if="site.auth_mode === 'oauth' && site.status === 'Connected'"
                  variant="subtle"
                  theme="blue"
                  size="sm"
                  :loading="isBusy('pull:' + site.name)"
                  :disabled="Boolean(busyAction && !isBusy('pull:' + site.name))"
                  label="Pull Accounts"
                  @click="openPullModal(site)"
                />
                <Button
                  v-if="site.auth_mode === 'oauth'"
                  variant="solid"
                  :theme="site.status === 'Connected' ? 'gray' : 'green'"
                  size="sm"
                  :loading="isBusy('authorize:' + site.name)"
                  :disabled="Boolean(busyAction && !isBusy('authorize:' + site.name))"
                  :label="site.status === 'Connected' ? 'Re-authorize' : 'Authorize'"
                  @click="authorizeSite(site, false)"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  :loading="isBusy('toggle:' + site.name)"
                  :disabled="Boolean(busyAction && !isBusy('toggle:' + site.name))"
                  :label="site.status === 'Connected' ? 'Disable' : 'Enable'"
                  @click="toggleSite(site)"
                />
              </div>

            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- Connect / Edit Site Dialog -->
    <Dialog
      v-model="siteDialogOpen"
      :title="isEditing ? 'Edit External Site' : 'Connect External Site'"
      size="xl"
    >
      <div class="space-y-4 py-2 text-sm">
        <p class="text-xs text-ink-gray-6">
          Connect your remote ERPNext or Frappe site to sync WhatsApp messages and contacts.
        </p>

        <!-- Step 1: Base details -->
        <div class="space-y-3 rounded-lg border border-outline-gray-2 p-4 bg-surface-gray-1">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-ink-gray-5">Step 1 · Remote Site</span>
            <span class="text-xs text-ink-gray-5">WhatsApp: <strong>{{ currentAccountLabel || 'Auto-create / Pull from site' }}</strong></span>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <TextInput
              v-model="siteForm.site_name"
              label="Site name"
              placeholder="e.g. Acme ERP"
              required
            />
            <TextInput
              v-model="siteForm.site_url"
              label="Site URL"
              placeholder="https://company.frappe.cloud"
              required
            />
          </div>
          <div class="flex justify-end pt-1">
            <Button
              size="sm"
              variant="subtle"
              :loading="isBusy('modal:prepare')"
              :disabled="Boolean(busyAction && !isBusy('modal:prepare'))"
              label="Prepare Setup"
              @click="saveOAuthApp('modal:prepare')"
            />
          </div>
        </div>

        <!-- Step 2: One-click setup in Frappe Desk -->
        <div v-if="preparedRedirectUri" class="space-y-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4">
          <div class="flex items-center justify-between">
            <span class="text-xs font-semibold uppercase tracking-wider text-ink-gray-5">Step 2 · Paste in External Site</span>
            <Button
              variant="solid"
              theme="green"
              size="sm"
              icon-left="lucide-clipboard-copy"
              label="Copy for Desk"
              @click="copyDeskPayload"
            />
          </div>

          <div class="rounded-lg bg-surface-base border border-outline-gray-2 p-3.5 text-xs text-ink-gray-7 space-y-2.5">
            <div class="flex items-start gap-2.5">
              <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-gray-2 font-semibold text-ink-gray-8 text-[11px]">1</span>
              <span>Click <strong>Copy for Desk</strong> above.</span>
            </div>
            <div class="flex items-start gap-2.5">
              <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-gray-2 font-semibold text-ink-gray-8 text-[11px]">2</span>
              <span>Open your external Frappe/ERPNext Desk and press <kbd class="px-1.5 py-0.5 rounded border border-outline-gray-2 bg-surface-gray-2 font-mono text-[11px] font-semibold text-ink-gray-9">Ctrl + V</kbd> anywhere on the page.</span>
            </div>
            <div class="flex items-start gap-2.5">
              <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-gray-2 font-semibold text-ink-gray-8 text-[11px]">3</span>
              <span>Frappe will automatically open the new <strong>OAuth Client</strong> form with all fields filled in. Click <strong>Save</strong>.</span>
            </div>
            <div class="flex items-start gap-2.5">
              <span class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-gray-2 font-semibold text-ink-gray-8 text-[11px]">4</span>
              <span>Copy the generated <strong>Client ID</strong> and <strong>Client Secret</strong> from your site and paste them in Step 3 below.</span>
            </div>
          </div>

          <div class="flex items-center justify-between text-xs text-ink-gray-5 pt-0.5">
            <span class="text-ink-gray-4">Alternative:</span>
            <button
              type="button"
              class="text-xs text-ink-gray-7 hover:underline flex items-center gap-1 font-mono"
              @click="copyToClipboard(preparedRedirectUri, 'Redirect URI')"
            >
              Copy Redirect URI manually
            </button>
          </div>
        </div>

        <!-- Step 3: Client credentials -->
        <div class="space-y-3 rounded-lg border border-outline-gray-2 p-4 bg-surface-gray-1">
          <div class="text-xs font-semibold uppercase tracking-wider text-ink-gray-5">Step 3 · Client Credentials</div>
          <p class="text-xs text-ink-gray-6">
            Enter the <strong>Client ID</strong> and <strong>Client Secret</strong> from the saved OAuth Client on your external site:
          </p>
          <div class="grid gap-3 sm:grid-cols-2">
            <TextInput
              v-model="siteForm.client_id"
              label="Client ID"
              placeholder="Paste Client ID"
            />
            <Password
              v-model="siteForm.client_secret"
              label="Client Secret"
              placeholder="Paste Client Secret"
            />
          </div>
        </div>
      </div>

      <template #actions>
        <div class="flex w-full items-center justify-between gap-2">
          <Button label="Cancel" @click="siteDialogOpen = false" />
          <div class="flex items-center gap-2">
            <Button
              variant="subtle"
              :loading="isBusy('modal:save')"
              :disabled="Boolean(busyAction && !isBusy('modal:save'))"
              label="Save Details"
              @click="saveOAuthApp('modal:save')"
            />
            <Button
              variant="solid"
              theme="green"
              :loading="isBusy('modal:authorize')"
              :disabled="Boolean(busyAction && !isBusy('modal:authorize'))"
              label="Save & Authorize (New Tab)"
              @click="handleAuthorizeFromModal"
            />
          </div>
        </div>
      </template>
    </Dialog>

    <!-- Verification Outcome Dialog -->
    <Dialog v-model="verifyOpen" :title="verifyOk ? 'Site Verified' : 'Could Not Verify Site'">
      <div class="space-y-3 py-2 text-sm">
        <p class="text-ink-gray-7">{{ verifyReason }}</p>
        <ul v-if="verifyChecks.length" class="space-y-2 rounded-lg border border-outline-gray-2 p-3 bg-surface-gray-1">
          <li v-for="check in verifyChecks" :key="check.name" class="flex items-start justify-between text-xs py-0.5">
            <span class="text-ink-gray-8">{{ check.name }}</span>
            <span :class="check.ok ? 'font-medium text-ink-green-7' : 'font-medium text-red-600'">
              {{ check.ok ? 'Passed' : 'Failed' }}
            </span>
          </li>
        </ul>
        <p v-if="verifyOk" class="text-xs text-ink-gray-6">Chats will now sync automatically to this external site.</p>
        <p v-else class="text-xs text-ink-gray-6">Fix any missing permissions or doc types on the external site, then verify again.</p>
      </div>
      <template #actions>
        <div class="flex items-center justify-end gap-2 w-full">
          <Button variant="subtle" label="Close" @click="verifyOpen = false"/>
          <Button
            v-if="verifyOk && lastVerifiedSite?.auth_mode === 'oauth'"
            variant="solid"
            theme="blue"
            label="Pull WhatsApp Accounts"
            @click="handlePullFromVerify"
          />
        </div>
      </template>
    </Dialog>

    <!-- Pull WhatsApp Accounts Dialog -->
    <Dialog
      v-model="pullDialogOpen"
      :title="`Pull WhatsApp Accounts from ${pullTargetSite?.site_name || pullTargetSite?.name || 'External Site'}`"
      size="lg"
    >
      <div class="space-y-4 py-2 text-sm">
        <p class="text-xs text-ink-gray-6">
          The following WhatsApp accounts were found on your external ERPNext/Frappe site. Select the accounts you want to import or sync with Nudg.
        </p>

        <div v-if="loadingRemoteAccounts" class="flex items-center justify-center py-8">
          <LoadingState label="Fetching WhatsApp accounts from external site..." />
        </div>

        <div v-else-if="!remoteAccounts.length" class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-6 text-center text-xs text-ink-gray-5">
          No WhatsApp accounts found on this external site. Make sure WA Accounts are configured on that site.
        </div>

        <div v-else class="space-y-3">
          <div class="flex items-center justify-between text-xs text-ink-gray-6 pb-1 border-b border-outline-gray-2">
            <span>{{ selectedRemoteAccounts.length }} of {{ remoteAccounts.length }} account(s) selected</span>
            <button class="text-ink-blue font-medium hover:underline cursor-pointer" @click="selectAllAccounts">
              {{ selectedRemoteAccounts.length === remoteAccounts.length ? 'Deselect All' : 'Select All' }}
            </button>
          </div>

          <div class="max-h-64 overflow-y-auto space-y-2">
            <div
              v-for="acc in remoteAccounts"
              :key="acc.name || acc.account_name"
              class="flex items-center justify-between p-3 rounded-lg border transition-colors cursor-pointer"
              :class="selectedRemoteAccounts.includes(acc.name || acc.account_name) ? 'border-outline-blue bg-surface-blue-1/20' : 'border-outline-gray-2 bg-surface-base'"
              @click="toggleSelectAccount(acc.name || acc.account_name)"
            >
              <div class="flex items-center gap-3">
                <input
                  type="checkbox"
                  class="rounded border-outline-gray-3 text-ink-blue focus:ring-ink-blue"
                  :checked="selectedRemoteAccounts.includes(acc.name || acc.account_name)"
                  @click.stop="toggleSelectAccount(acc.name || acc.account_name)"
                />
                <div>
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-ink-gray-9">{{ acc.account_name || acc.name }}</span>
                    <Badge
                      size="sm"
                      :theme="acc.exists_locally ? 'blue' : 'green'"
                      :label="acc.exists_locally ? 'Update Existing' : 'New Account'"
                    />
                  </div>
                  <div class="mt-0.5 text-xs text-ink-gray-5 flex flex-wrap gap-x-3 gap-y-0.5">
                    <span v-if="acc.phone_id">Phone ID: <code>{{ acc.phone_id }}</code></span>
                    <span v-if="acc.business_id">WABA: <code>{{ acc.business_id }}</code></span>
                    <span v-if="acc.app_id">App ID: <code>{{ acc.app_id }}</code></span>
                  </div>
                </div>
              </div>
              <Badge
                size="sm"
                :theme="acc.status === 'Active' ? 'green' : 'gray'"
                :label="acc.status"
              />
            </div>
          </div>
        </div>
      </div>

      <template #actions>
        <div class="flex justify-end gap-2">
          <Button variant="subtle" label="Cancel" @click="pullDialogOpen = false" />
          <Button
            v-if="remoteAccounts.length"
            variant="solid"
            theme="blue"
            :loading="busyAction === 'pull:confirm'"
            :disabled="!selectedRemoteAccounts.length || Boolean(busyAction)"
            label="Pull Accounts"
            @click="confirmPullAccounts"
          />
        </div>
      </template>
    </Dialog>

  </div>
</template>
