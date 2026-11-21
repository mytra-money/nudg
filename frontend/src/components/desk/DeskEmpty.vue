<script setup lang="ts">
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import ErrorState from '@/components/ErrorState.vue'

/**
 * Unified empty / loading / error / no-account block for manager pages.
 */
withDefaults(
  defineProps<{
    kind?: 'empty' | 'loading' | 'error' | 'account'
    title?: string
    description?: string
    message?: string
    compact?: boolean
    allowRetry?: boolean
  }>(),
  {
    kind: 'empty',
    allowRetry: false,
  },
)

const emit = defineEmits<{
  retry: []
}>()

const defaults: Record<string, { title: string; description: string }> = {
  account: {
    title: 'No WhatsApp account connected',
    description: 'Connect a WhatsApp number before using this page.',
  },
  empty: {
    title: 'Nothing here yet',
    description: '',
  },
  loading: {
    title: 'Loading…',
    description: '',
  },
  error: {
    title: 'Something went wrong',
    description: '',
  },
}
</script>

<template>
  <LoadingState v-if="kind === 'loading'" :label="title || defaults.loading.title" />
  <ErrorState
    v-else-if="kind === 'error'"
    :title="title || defaults.error.title"
    :message="message || description || 'Please try again.'"
    :allow-retry="allowRetry"
    @retry="emit('retry')"
  />
  <EmptyState
    v-else
    :title="title || (kind === 'account' ? defaults.account.title : defaults.empty.title)"
    :description="
      description ??
      (kind === 'account' ? defaults.account.description : defaults.empty.description)
    "
    :compact="compact"
  >
    <template v-if="$slots.icon" #icon>
      <slot name="icon" />
    </template>
    <slot />
  </EmptyState>
</template>
