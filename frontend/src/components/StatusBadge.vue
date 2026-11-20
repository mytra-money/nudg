<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  label: string
  tone?: 'green' | 'amber' | 'red' | 'gray' | 'blue' | 'teal' | 'purple'
}>()

const known: Record<string, NonNullable<typeof props.tone>> = {
  Connected: 'green',
  Active: 'green',
  Approved: 'green',
  Ready: 'green',
  Synced: 'green',
  On: 'green',
  Enabled: 'green',
  Success: 'green',
  Completed: 'green',
  Info: 'green',
  Pending: 'amber',
  Unassigned: 'amber',
  Warning: 'amber',
  Failed: 'red',
  Error: 'red',
  Rejected: 'red',
  Disabled: 'red',
  Blocked: 'red',
  Draft: 'gray',
  Off: 'gray',
  Deleted: 'gray',
  Inactive: 'gray',
}

const styles: Record<string, string> = {
  green: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20',
  amber: 'bg-amber-50 text-amber-800 ring-amber-600/20',
  red: 'bg-red-50 text-red-700 ring-red-600/20',
  gray: 'bg-surface-gray-2 text-ink-gray-6 ring-outline-gray-2',
  blue: 'bg-blue-50 text-blue-700 ring-blue-600/20',
  teal: 'bg-teal-50 text-[#075E54] ring-[#075E54]/20',
  purple: 'bg-purple-50 text-purple-700 ring-purple-600/20',
}

const tone = computed(() => props.tone || known[props.label] || 'gray')
</script>

<template>
  <span
    class="inline-flex h-5 max-w-full shrink-0 items-center rounded-full px-2 text-[11px] font-medium leading-none ring-1 ring-inset"
    :class="styles[tone]"
  >
    <span class="truncate">{{ label }}</span>
  </span>
</template>
