<script setup lang="ts">
defineProps<{
  title: string
  description?: string
  compact?: boolean
}>()
</script>

<template>
  <div :class="compact ? 'px-3 py-4 text-center' : 'mx-auto flex max-w-md flex-col items-center justify-center px-4 py-12 text-center'">
    <div v-if="!compact" class="mb-3 grid size-12 place-items-center rounded-full bg-surface-gray-2 text-ink-gray-5 shadow-2xs">
      <slot name="icon">
        <span class="lucide-inbox size-6 text-ink-gray-4" aria-hidden="true" />
      </slot>
    </div>
    <h2 class="text-sm font-semibold text-ink-gray-9">{{ title }}</h2>
    <p v-if="description" class="mt-1 text-xs leading-relaxed text-ink-gray-6 max-w-sm">{{ description }}</p>
    <div v-if="$slots.default" class="mt-4">
      <slot />
    </div>
  </div>
</template>
