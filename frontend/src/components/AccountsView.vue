<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button, Dialog, TextInput } from 'frappe-ui'
import DeskCard from '@/components/desk/DeskCard.vue'
import EmbeddedSignup from '@/components/EmbeddedSignup.vue'
import EmptyState from '@/components/EmptyState.vue'
import ManualConnectDialog from '@/components/ManualConnectDialog.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useDesk } from '@/stores/desk'
import { accounts as sampleAccounts } from '@/mocks/sample'
import type { Account } from '@/types'

const desk = useDesk()
const searchQuery = ref('')
const showConnectModal = ref(false)
const showCredentialsModal = ref(false)

onMounted(() => {
  desk.load()
})

async function onConnected() {
  await desk.load()
}

function onManualConnected() {
  showCredentialsModal.value = false
  showConnectModal.value = false
  void desk.load()
}

const accountsList = computed(() => {
  if (desk.inbox.value?.accounts && desk.inbox.value.accounts.length > 0) {
    return desk.inbox.value.accounts
  }
  return desk.mode.value === 'sample' ? sampleAccounts : []
})

const filteredAccounts = computed(() => {
  return accountsList.value.filter((acc: Account) => {
    const matchesSearch =
      !searchQuery.value ||
      acc.account_name.toLowerCase().includes(searchQuery.value.toLowerCase())
    if (!matchesSearch) return false
    return true
  })
})
</script>

<template>
  <div class="h-full overflow-y-auto bg-white px-4 py-6 md:px-8">
    <div class="flex flex-col gap-4 border-b border-outline-gray-2 pb-6 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-ink-gray-9">WhatsApp numbers</h1>
        <p class="text-sm text-ink-gray-6">Connect a number, then use it from the inbox.</p>
      </div>
      <Button
        variant="solid"
        class="bg-[#075E54] text-white hover:bg-[#128C7E]"
        label="Connect number"
        @click="showConnectModal = true"
      />
    </div>

    <div v-if="accountsList.length === 0" class="mt-8 rounded-xl border border-outline-gray-2 bg-white p-8 text-center">
      <h2 class="text-sm font-semibold text-ink-gray-9">No WhatsApp number yet</h2>
      <p class="mx-auto mt-1 max-w-md text-xs text-ink-gray-6">
        Connect with Facebook, or enter credentials if this number is already on the WhatsApp Cloud API.
      </p>
      <Button
        variant="solid"
        class="mt-4 bg-[#075E54] text-white hover:bg-[#128C7E]"
        label="Connect number"
        @click="showConnectModal = true"
      />
    </div>

    <div v-else class="mt-6">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-sm text-ink-gray-7">{{ accountsList.length }} connected</p>
        <TextInput
          v-model="searchQuery"
          placeholder="Search numbers"
          class="w-full sm:w-48"
        />
      </div>
      <div class="mt-4 grid gap-3 md:grid-cols-2">
        <DeskCard
          v-for="account in filteredAccounts"
          :key="account.name"
          class="!p-4"
        >
          <div class="flex items-start justify-between gap-3">
            <h2 class="min-w-0 truncate text-base font-semibold text-ink-gray-9">{{ account.account_name }}</h2>
            <StatusBadge :label="account.status || 'Inactive'" />
          </div>
          <p v-if="account.is_default" class="mt-2 text-xs font-medium text-[#075E54]">Default number</p>
        </DeskCard>
      </div>
      <EmptyState v-if="filteredAccounts.length === 0" compact title="No numbers match" description="Try a different name." />
    </div>

    <Dialog v-model="showConnectModal" title="Connect WhatsApp">
      <div class="py-1">
        <p class="text-sm text-ink-gray-7">Choose how to connect this number.</p>
        <div class="mt-4">
          <EmbeddedSignup @connected="onConnected" @manual="showCredentialsModal = true" />
        </div>
      </div>
      <template #actions>
        <div class="flex w-full justify-end">
          <Button variant="solid" class="!bg-[#e5e7eb] !text-[#111827] hover:!bg-[#d1d5db]" label="Close" @click="showConnectModal = false" />
        </div>
      </template>
    </Dialog>

    <ManualConnectDialog v-model="showCredentialsModal" @connected="onManualConnected" />
  </div>
</template>
