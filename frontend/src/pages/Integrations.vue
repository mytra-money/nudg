<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AccountsView from '@/components/AccountsView.vue'
import { useDesk } from '@/stores/desk'

const desk = useDesk()
const route = useRoute()
const showLogs = computed(() => desk.inbox.value?.can_read_logs !== false)

const connectedAccounts = computed(
  () => (desk.inbox.value?.accounts || []).filter((account) => account.status === 'Active').length,
)
const isAccountsActive = computed(() => route.path === '/integrations' || route.path === '/accounts')
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-surface-gray-2/60">
    <!-- Sub-navigation Header -->
    <header class="flex flex-wrap items-center justify-between border-b border-outline-gray-2 bg-white px-4 py-2 sm:px-6">
      <div class="flex items-center gap-1 sm:gap-2">
        <RouterLink
          to="/integrations"
          class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold sm:text-sm transition-all"
          :class="
            isAccountsActive
              ? 'bg-[#075E54]/10 text-[#075E54] border border-[#075E54]/20 shadow-xs'
              : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9'
          "
        >
          <span class="lucide-radio size-4" />
          <span>WhatsApp numbers</span>
        </RouterLink>

        <RouterLink
          to="/integrations/erpnext"
          class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold sm:text-sm transition-all"
          :class="
            route.path.includes('/erpnext')
              ? 'bg-[#075E54]/10 text-[#075E54] border border-[#075E54]/20 shadow-xs'
              : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9'
          "
        >
          <span class="lucide-building-2 size-4" />
          <span>ERPNext</span>
        </RouterLink>

        <RouterLink
          v-if="showLogs"
          to="/integrations/logs"
          class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold sm:text-sm transition-all"
          :class="
            route.path.includes('/logs')
              ? 'bg-[#075E54]/10 text-[#075E54] border border-[#075E54]/20 shadow-xs'
              : 'text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9'
          "
        >
          <span class="lucide-scroll-text size-4" />
          <span>Logs</span>
        </RouterLink>
      </div>

      <div class="hidden items-center gap-3 sm:flex">
        <span
          class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset"
          :class="connectedAccounts ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20' : 'bg-surface-gray-2 text-ink-gray-6 ring-outline-gray-2'"
        >
          <span class="h-1.5 w-1.5 rounded-full" :class="connectedAccounts ? 'bg-emerald-500' : 'bg-ink-gray-4'"></span>
          {{ connectedAccounts ? 'WhatsApp account connected' : 'No WhatsApp account connected' }}
        </span>
      </div>
    </header>

    <!-- Main Content Body -->
    <div class="min-h-0 flex-1">
      <AccountsView />
    </div>
  </div>
</template>
