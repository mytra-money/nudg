<script setup lang="ts">
/**
 * Shared content panel when frappe-ui has no generic Card.
 * Surface tokens match ChartCard / NumberCard (rounded-4, outline-gray-1).
 */
withDefaults(
  defineProps<{
    title?: string
    description?: string
    /** Extra padding around the body (default true). */
    padding?: boolean
    /** Hover affordance for clickable tiles. */
    interactive?: boolean
    as?: 'div' | 'section' | 'article' | 'a' | 'button'
    href?: string
    /** Soft teal surface for policy / tip panels. */
    tone?: 'default' | 'accent'
  }>(),
  {
    padding: true,
    interactive: false,
    as: 'section',
    tone: 'default',
  },
)
</script>

<template>
  <component
    :is="as"
    :href="as === 'a' ? href : undefined"
    :type="as === 'button' ? 'button' : undefined"
    class="relative min-w-0 overflow-hidden rounded-4 border"
    :class="[
      tone === 'accent'
        ? 'border-teal-200/60 bg-gradient-to-br from-teal-50/70 to-emerald-50/40'
        : 'border-outline-gray-1 bg-surface-elevation-2',
      padding ? 'p-5' : '',
      interactive || as === 'a' || as === 'button'
        ? 'transition-colors hover:border-outline-gray-3 hover:bg-surface-gray-1'
        : '',
      as === 'button' ? 'w-full cursor-pointer text-left' : '',
    ]"
  >
    <div
      v-if="title || $slots.header || $slots.actions"
      class="mb-3 flex items-start justify-between gap-3 border-b border-outline-gray-1 pb-3"
    >
      <div class="min-w-0">
        <slot name="header">
          <h3
            v-if="title"
            class="text-base font-semibold"
            :class="tone === 'accent' ? 'text-ink-green-7' : 'text-ink-gray-9'"
          >
            {{ title }}
          </h3>
          <p v-if="description" class="mt-0.5 text-xs text-ink-gray-5">{{ description }}</p>
        </slot>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
    <slot />
  </component>
</template>
