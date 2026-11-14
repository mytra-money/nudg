<script setup lang="ts">
import { ref } from 'vue'
import { Button, call, Dialog, toast } from 'frappe-ui'

const open = defineModel<boolean>({ default: false })
const emit = defineEmits<{ connected: [] }>()

const accountName = ref('')
const phoneId = ref('')
const accessToken = ref('')
const businessId = ref('')
const appId = ref('')
const saving = ref(false)

function reset() {
  accountName.value = ''
  phoneId.value = ''
  accessToken.value = ''
  businessId.value = ''
  appId.value = ''
}

async function save() {
  if (!accountName.value.trim() || !phoneId.value.trim() || !accessToken.value.trim()) {
    toast.error('Enter the account name, phone number ID, and access token.')
    return
  }
  saving.value = true
  try {
    await call('nudg.desk_api.create_whatsapp_account', {
      account_name: accountName.value.trim(),
      phone_id: phoneId.value.trim(),
      access_token: accessToken.value.trim(),
      business_id: businessId.value.trim() || undefined,
      app_id: appId.value.trim() || undefined,
    })
    toast.success('WhatsApp number connected.')
    reset()
    open.value = false
    emit('connected')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Could not connect this number.')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog v-model="open" title="Enter WhatsApp credentials">
    <div class="grid grid-cols-1 gap-4 py-1 text-xs sm:grid-cols-2">
      <p class="sm:col-span-2 text-ink-gray-6">
        Use this if the number is already on the WhatsApp Cloud API and you have its token.
      </p>
      <label class="sm:col-span-2 block font-semibold text-ink-gray-8">
        Account name <span class="text-red-500">*</span>
        <input v-model="accountName" type="text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 font-normal text-ink-gray-9" placeholder="Support" />
      </label>
      <label class="block font-semibold text-ink-gray-8">
        Phone number ID <span class="text-red-500">*</span>
        <input v-model="phoneId" type="text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 font-normal text-ink-gray-9" placeholder="108928374928172" />
      </label>
      <label class="block font-semibold text-ink-gray-8">
        WhatsApp account ID
        <input v-model="businessId" type="text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 font-normal text-ink-gray-9" placeholder="102938475619283" />
      </label>
      <label class="sm:col-span-2 block font-semibold text-ink-gray-8">
        Access token <span class="text-red-500">*</span>
        <input v-model="accessToken" type="password" autocomplete="off" class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 font-mono font-normal text-ink-gray-9" />
      </label>
      <label class="block font-semibold text-ink-gray-8">
        Meta app ID
        <input v-model="appId" type="text" class="mt-1 block w-full rounded-lg border border-outline-gray-2 bg-white px-3 py-2 font-normal text-ink-gray-9" />
      </label>
    </div>
    <template #actions>
      <div class="flex w-full items-center justify-end gap-2">
        <Button variant="subtle" label="Cancel" @click="open = false" />
        <Button variant="solid" class="bg-[#075E54] text-white hover:bg-[#128C7E]" :loading="saving" label="Connect number" @click="save" />
      </div>
    </template>
  </Dialog>
</template>
