<script setup lang="ts">
import { ref } from 'vue'
import { Button, call, Dialog, FormControl, Password, toast } from 'frappe-ui'
import { userFacingError } from '@/utils/errors'

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
    toast.error(userFacingError(err, 'Could not connect this number.'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog v-model="open" title="Enter WhatsApp credentials">
    <div class="grid grid-cols-1 gap-4 py-1 sm:grid-cols-2">
      <p class="text-xs text-ink-gray-6 sm:col-span-2">
        Use this if the number is already on the WhatsApp Cloud API and you have its token.
      </p>
      <FormControl
        v-model="accountName"
        type="text"
        label="Account name"
        placeholder="Support"
        required
        class="sm:col-span-2"
      />
      <FormControl
        v-model="phoneId"
        type="text"
        label="Phone number ID"
        placeholder="108928374928172"
        required
      />
      <FormControl
        v-model="businessId"
        type="text"
        label="WhatsApp account ID"
        placeholder="102938475619283"
      />
      <Password
        v-model="accessToken"
        label="Access token"
        autocomplete="off"
        required
        class="sm:col-span-2"
      />
      <FormControl v-model="appId" type="text" label="Meta app ID" />
    </div>
    <template #actions>
      <div class="flex w-full items-center justify-end gap-2">
        <Button variant="subtle" label="Cancel" @click="open = false" />
        <Button
          variant="solid"
          class="bg-[#075E54] text-white hover:bg-[#128C7E]"
          :loading="saving"
          label="Connect number"
          @click="save"
        />
      </div>
    </template>
  </Dialog>
</template>
