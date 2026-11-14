<script setup lang="ts">
import EmptyState from '@/components/EmptyState.vue'

defineProps<{
  title: string
}>()
</script>

<template>
  <EmptyState
    :title="`${title} is not available yet`"
    :description="`${title} is part of the NUDG shell. This module is not available yet.`"
  />
</template>
