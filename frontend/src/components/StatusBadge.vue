<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'

const props = defineProps<{
  label: string
  tone?: 'green' | 'amber' | 'red' | 'gray' | 'blue' | 'teal' | 'purple'
}>()

type BadgeTheme = 'gray' | 'blue' | 'green' | 'amber' | 'red' | 'violet'

const known: Record<string, BadgeTheme> = {
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

const toneMap: Record<NonNullable<typeof props.tone>, BadgeTheme> = {
  green: 'green',
  amber: 'amber',
  red: 'red',
  gray: 'gray',
  blue: 'blue',
  teal: 'blue',
  purple: 'violet',
}

const theme = computed<BadgeTheme>(() => {
  if (props.tone) return toneMap[props.tone]
  return known[props.label] || 'gray'
})
</script>

<template>
  <Badge :label="label" :theme="theme" variant="subtle" size="sm" />
</template>
