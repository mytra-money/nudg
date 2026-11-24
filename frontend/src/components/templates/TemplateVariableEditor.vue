<script setup lang="ts">
import { TextInput } from 'frappe-ui'

withDefaults(
  defineProps<{
    names: string[]
    values: Record<string, string>
    hints?: Record<string, string>
    compact?: boolean
  }>(),
  { compact: false },
)

const emit = defineEmits<{ update: [name: string, value: string] }>()

function token(name: string) {
  return `{{${name}}}`
}
</script>

<template>
  <div v-if="names.length" :class="compact ? 'flex items-center gap-3' : 'space-y-2.5'">
    <p v-if="compact" class="max-w-[12rem] shrink-0 text-[11px] leading-snug text-ink-gray-6">
      Preview samples. The saved template does not change.
    </p>
    <p v-else class="text-xs font-semibold text-ink-gray-8">Sample values</p>
    <div :class="compact ? 'flex min-w-0 flex-1 items-center gap-3 overflow-x-auto' : 'grid grid-cols-1 gap-2.5'">
      <div
        v-for="name in names"
        :key="name"
        :class="compact ? 'flex shrink-0 items-center gap-2' : 'space-y-1'"
      >
        <span v-if="compact" class="shrink-0 font-mono text-xs text-ink-gray-7">{{ token(name) }}</span>
        <TextInput
          :class="compact ? 'w-36' : ''"
          :label="compact ? undefined : token(name)"
          :aria-label="compact ? token(name) : undefined"
          :model-value="values[name] ?? ''"
          @update:model-value="(value) => emit('update', name, String(value ?? ''))"
        />
        <p v-if="hints?.[name] && !compact" class="font-mono text-[11px] text-ink-gray-5">{{ hints[name] }}</p>
      </div>
    </div>
  </div>
</template>
