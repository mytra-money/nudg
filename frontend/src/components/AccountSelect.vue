<script setup lang="ts">
import { computed, inject } from 'vue'
import { Select, sidebarCollapsedKey } from 'frappe-ui'
import { useDesk } from '@/stores/desk'

const props = defineProps<{ inline?: boolean }>()
const desk = useDesk()
const collapsed = inject(sidebarCollapsedKey, computed(() => false))

const options = computed(() =>
  (desk.inbox.value?.accounts || []).map((row) => ({
    label: row.account_name || row.name,
    value: row.name,
    description: row.is_default ? 'Default number' : row.status,
  })),
)

function onUpdate(value: string | number | null | undefined) {
  const next = value == null ? '' : String(value)
  if (!next || next === 'all') return
  void desk.setAccount(next)
}
</script>

<template>
  <div v-show="props.inline || !collapsed" :class="props.inline ? 'min-w-0' : 'px-2 pb-2'">
    <Select
      :model-value="desk.account.value"
      :options="options"
      :disabled="!options.length"
      placeholder="Select number"
      @update:model-value="onUpdate"
    />
  </div>
</template>
