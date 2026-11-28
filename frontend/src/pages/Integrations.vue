<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
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
  <div class="flex h-full min-h-0 flex-col bg-surface-base">
    <!-- Sub-navigation Header -->
    <header class="flex flex-wrap items-center justify-between border-b border-outline-gray-2 bg-surface-base px-4 py-2 sm:px-6">
      <div class="flex items-center gap-1 sm:gap-2">
        <Button
          route="/integrations"
          size="sm"
          icon-left="lucide-radio"
          label="WhatsApp numbers"
          :variant="isAccountsActive ? 'subtle' : 'ghost'"
          :theme="isAccountsActive ? 'green' : 'gray'"
          :data-state="isAccountsActive ? 'active' : undefined"
        />

        <Button
          v-if="showLogs"
          route="/integrations/logs"
          size="sm"
          icon-left="lucide-scroll-text"
          label="Logs"
          :variant="route.path.includes('/logs') ? 'subtle' : 'ghost'"
          :theme="route.path.includes('/logs') ? 'green' : 'gray'"
          :data-state="route.path.includes('/logs') ? 'active' : undefined"
        />
      </div>

      <div v-if="!connectedAccounts" class="hidden items-center gap-3 sm:flex">
        <Badge theme="gray" variant="subtle" label="No WhatsApp account connected" />
      </div>
    </header>

    <!-- Main Content Body -->
    <div class="min-h-0 flex-1">
      <AccountsView />
    </div>
  </div>
</template>
