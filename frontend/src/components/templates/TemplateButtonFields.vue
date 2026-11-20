<script setup lang="ts">
import { Button, FormControl } from 'frappe-ui'

defineProps<{
  disabled?: boolean
}>()

const button = defineModel<{
  button_type: string
  button_text: string
  url: string
  phone_number: string
}>({ required: true })

const emit = defineEmits<{
  remove: []
}>()

const buttonTypeOptions = [
  { label: 'Quick Reply', value: 'Quick Reply' },
  { label: 'URL', value: 'URL' },
  { label: 'Phone Number', value: 'Phone Number' },
  { label: 'Copy Code', value: 'Copy Code' },
  { label: 'Voice Call', value: 'Voice Call' },
]
</script>

<template>
  <div class="grid grid-cols-1 gap-2 rounded-lg border border-outline-gray-2 p-2 sm:grid-cols-2">
    <FormControl
      v-model="button.button_type"
      type="select"
      label="Button type"
      :options="buttonTypeOptions"
      :disabled="disabled"
    />
    <FormControl
      v-model="button.button_text"
      type="text"
      label="Button label"
      :disabled="disabled"
    />
    <FormControl
      v-if="button.button_type === 'URL'"
      v-model="button.url"
      type="url"
      label="URL"
      placeholder="https://"
      class="sm:col-span-2"
      :disabled="disabled"
    />
    <FormControl
      v-else-if="button.button_type === 'Phone Number'"
      v-model="button.phone_number"
      type="tel"
      label="Phone number"
      class="sm:col-span-2"
      :disabled="disabled"
    />
    <div class="sm:col-span-2">
      <Button size="sm" variant="ghost" label="Remove" :disabled="disabled" @click="emit('remove')" />
    </div>
  </div>
</template>
