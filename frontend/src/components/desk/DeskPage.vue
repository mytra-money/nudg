<script setup lang="ts">
/**
 * Content shell under AppShell.
 * The shell navbar owns the page title — this component never repeats an h1.
 * Desk canvas is white to match the product shell.
 * - studio: action strip + kpi/toolbar + non-scrolling body
 * - scroll: padded scrollable body with optional actions/tabs/kpi/toolbar
 */
withDefaults(
  defineProps<{
    variant?: 'studio' | 'scroll'
  }>(),
  {
    variant: 'studio',
  },
)
</script>

<template>
  <div class="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-white">
    <!-- Studio: compact actions only (no page title — AppShell shows it) -->
    <header
      v-if="variant === 'studio' && $slots.actions"
      class="flex shrink-0 flex-wrap items-center justify-end gap-2 border-b border-outline-gray-2 bg-white px-4 py-2.5"
    >
      <slot name="actions" />
    </header>

    <div
      v-if="variant === 'scroll'"
      class="flex min-h-0 flex-1 flex-col overflow-y-auto bg-white px-4 py-5 sm:px-8"
    >
      <div
        v-if="$slots.actions || $slots.badges"
        class="mb-5 flex flex-wrap items-center justify-between gap-2"
      >
        <div v-if="$slots.badges" class="flex flex-wrap items-center gap-2">
          <slot name="badges" />
        </div>
        <div v-if="$slots.actions" class="ml-auto flex flex-wrap items-center gap-2">
          <slot name="actions" />
        </div>
      </div>

      <div v-if="$slots.tabs" class="mb-5 overflow-x-auto">
        <slot name="tabs" />
      </div>

      <div v-if="$slots.kpi" class="mb-5">
        <slot name="kpi" />
      </div>

      <div v-if="$slots.toolbar" class="mb-5">
        <slot name="toolbar" />
      </div>

      <div class="min-h-0 flex-1">
        <slot />
      </div>
    </div>

    <template v-if="variant === 'studio'">
      <div v-if="$slots.kpi" class="shrink-0 border-b border-outline-gray-2 bg-white px-4 py-3">
        <slot name="kpi" />
      </div>
      <div v-if="$slots.toolbar" class="shrink-0 border-b border-outline-gray-2 bg-white px-4 py-2.5">
        <slot name="toolbar" />
      </div>
      <div class="flex min-h-0 flex-1 flex-col overflow-hidden bg-white">
        <slot />
      </div>
    </template>
  </div>
</template>
