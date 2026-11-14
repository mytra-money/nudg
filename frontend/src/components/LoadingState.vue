<script setup lang="ts">
import { Spinner } from 'frappe-ui'

defineProps<{
  label?: string
}>()
</script>

<template>
  <div class="grid min-h-48 place-items-center px-4 py-16" role="status" aria-live="polite">
    <div class="flex flex-col items-center gap-3">
      <Spinner class="size-6 text-[#075E54]" />
      <p class="text-xs font-medium text-ink-gray-6">{{ label || 'Loading…' }}</p>
    </div>
  </div>
</template>
