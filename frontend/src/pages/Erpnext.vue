<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Button, call, toast } from 'frappe-ui'
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { errorText } from '@/utils/format'
import { useDesk } from '@/stores/desk'

const desk = useDesk()
const live = computed(() => Boolean(window.csrf_token))
const loading = ref(true)
const error = ref<string | null>(null)
const busy = ref(false)
const sites = ref<any[]>([])
const accounts = computed(() => desk.inbox.value?.accounts || [])

const siteForm = ref({
  site_name: '',
  site_url: '',
  api_key: '',
  api_secret: '',
  whatsapp_account: '',
})

async function load() {
  if (!live.value) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = null
  try {
    sites.value = (await call<any[]>('nudg.integrations.erpnext.api.list_sites')) || []
    if (!siteForm.value.whatsapp_account && accounts.value.length) {
      siteForm.value.whatsapp_account = accounts.value[0].name
    }
  } catch (err) {
    error.value = errorText(err)
  } finally {
    loading.value = false
  }
}

async function connect() {
  busy.value = true
  try {
    await call('nudg.integrations.erpnext.api.connect_site', { ...siteForm.value })
    siteForm.value.api_key = ''
    siteForm.value.api_secret = ''
    toast.success('ERPNext site connected. Alerts are still configured on that site.')
    await load()
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busy.value = false
  }
}

async function toggleSite(site: any) {
  busy.value = true
  try {
    await call('nudg.integrations.erpnext.api.set_site_enabled', {
      site: site.name,
      enabled: site.status === 'Connected' ? 0 : 1,
    })
    await load()
  } catch (err) {
    toast.error(errorText(err))
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-surface-gray-2/60">
    <header class="flex flex-wrap items-center gap-2 border-b border-outline-gray-2 bg-white px-4 py-2 sm:px-6">
      <RouterLink to="/integrations" class="rounded-lg px-3 py-1.5 text-sm font-semibold text-ink-gray-6 hover:bg-surface-gray-2">WhatsApp numbers</RouterLink>
      <RouterLink to="/integrations/erpnext" class="rounded-lg border border-[#075E54]/20 bg-[#075E54]/10 px-3 py-1.5 text-sm font-semibold text-[#075E54]">ERPNext</RouterLink>
      <RouterLink to="/integrations/catalogs" class="rounded-lg px-3 py-1.5 text-sm font-semibold text-ink-gray-6 hover:bg-surface-gray-2">Catalogs</RouterLink>
    </header>

    <div class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex max-w-3xl flex-col gap-6">
        <section class="rounded-xl border border-outline-gray-2 bg-white p-4">
          <h1 class="text-lg font-semibold text-ink-gray-9">ERPNext</h1>
          <p class="mt-1 text-sm text-ink-gray-6">
            Connect the site so Nudge can send on its WhatsApp number. Invoice and other document alerts stay on that site, in Notification, with channel WhatsApp. Nudge does not keep a copy of those rules. Chat and campaigns keep working when the site is down.
          </p>
        </section>

        <LoadingState v-if="loading" />
        <ErrorState v-else-if="error" :message="error" allow-retry @retry="load" />
        <section v-else class="rounded-xl border border-outline-gray-2 bg-white p-4">
          <h2 class="text-sm font-semibold text-ink-gray-9">Connect a site</h2>
          <p v-if="!live" class="mt-2 text-sm text-ink-gray-6">Open Nudge on a signed-in site to connect ERPNext.</p>
          <form v-else class="mt-3 grid gap-3 sm:grid-cols-2" @submit.prevent="connect">
            <input v-model="siteForm.site_name" required placeholder="Site name" class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" />
            <input v-model="siteForm.site_url" required placeholder="https://company.frappe.cloud" class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" />
            <input v-model="siteForm.api_key" required placeholder="API key" class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" />
            <input v-model="siteForm.api_secret" required type="password" placeholder="API secret" class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm" />
            <select v-model="siteForm.whatsapp_account" required class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm">
              <option value="" disabled>WhatsApp account</option>
              <option v-for="account in accounts" :key="account.name" :value="account.name">{{ account.account_name || account.name }}</option>
            </select>
            <Button variant="solid" :loading="busy" type="submit">Connect</Button>
          </form>
          <ul class="mt-4 divide-y divide-outline-gray-2">
            <li v-for="site in sites" :key="site.name" class="flex items-center justify-between gap-3 py-2 text-sm">
              <div>
                <div class="font-medium text-ink-gray-9">{{ site.name }}</div>
                <div class="text-ink-gray-6">{{ site.site_url }} · {{ site.status }} · {{ site.whatsapp_account }}</div>
                <div v-if="site.last_error" class="text-red-600">{{ site.last_error }}</div>
              </div>
              <Button variant="subtle" :loading="busy" @click="toggleSite(site)">{{ site.status === 'Connected' ? 'Disable' : 'Enable' }}</Button>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>
