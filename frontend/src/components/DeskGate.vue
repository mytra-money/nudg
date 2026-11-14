<script setup lang="ts">
import ErrorState from '@/components/ErrorState.vue'
import LoadingState from '@/components/LoadingState.vue'
import { useDesk } from '@/stores/desk'

const desk = useDesk()

function retry() {
  void desk.load()
}
</script>

<template>
  <LoadingState v-if="desk.loading.value" label="Loading WhatsApp data…" />
  <ErrorState
    v-else-if="desk.error.value"
    title="The desk could not load."
    :message="desk.error.value"
    allow-retry
    @retry="retry"
  />
  <slot v-else />
</template>
