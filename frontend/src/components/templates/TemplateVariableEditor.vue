<script setup lang="ts">
import { TextInput } from 'frappe-ui'

defineProps<{
  names: string[]
  values: Record<string, string>
  hints?: Record<string, string>
}>()

const emit = defineEmits<{ update: [name: string, value: string] }>()

function token(name: string) {
  return `{{${name}}}`
}
</script>

<template>
  <div v-if="names.length" class="space-y-2">
    <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Sample values</p>
    <div class="grid max-h-48 grid-cols-1 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
      <div v-for="name in names" :key="name" class="space-y-1">
        <TextInput
          :label="token(name)"
          :model-value="values[name] ?? ''"
          @update:model-value="(value) => emit('update', name, String(value ?? ''))"
        />
        <p v-if="hints?.[name]" class="font-mono text-[11px] text-ink-gray-5">{{ hints[name] }}</p>
      </div>
    </div>
  </div>
</template>
