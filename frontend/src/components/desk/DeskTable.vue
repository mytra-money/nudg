<script setup lang="ts">
/**
 * Consistent table chrome for Settings team list, snapshot history, etc.
 */
withDefaults(
  defineProps<{
    /** Extra classes on the outer scroll wrapper. */
    class?: string
  }>(),
  {},
)
</script>

<template>
  <div
    class="overflow-x-auto rounded-4 border border-outline-gray-1 bg-surface-elevation-2"
    :class="$props.class"
  >
    <table class="min-w-full divide-y divide-outline-gray-1 text-left text-xs">
      <thead v-if="$slots.head" class="bg-surface-gray-1 text-[11px] font-semibold uppercase tracking-wide text-ink-gray-5">
        <slot name="head" />
      </thead>
      <tbody class="divide-y divide-outline-gray-1 bg-white">
        <slot />
      </tbody>
    </table>
  </div>
</template>
