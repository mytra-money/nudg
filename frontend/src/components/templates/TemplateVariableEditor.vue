<script setup lang="ts">
import { TextInput } from 'frappe-ui'

defineProps<{
  names: string[]
  values: Record<string, string>
}>()

const emit = defineEmits<{ update: [name: string, value: string] }>()

function token(name: string) {
  return `{{${name}}}`
}
</script>

<template>
  <div v-if="names.length" class="space-y-2">
    <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Sample values</p>
    <div class="max-h-48 space-y-2 overflow-y-auto pr-1">
      <TextInput
        v-for="name in names"
        :key="name"
        :label="token(name)"
        :model-value="values[name] ?? ''"
        @update:model-value="(value) => emit('update', name, String(value ?? ''))"
      />
    </div>
  </div>
</template>
