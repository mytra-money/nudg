<script setup lang="ts">
/**
 * Master / detail split used by Templates, Marketing, Catalogs.
 * On narrow viewports, showDetail toggles which pane is visible.
 * Panes use the white desk canvas.
 */
withDefaults(
  defineProps<{
    /** CSS grid-template-columns for md+ breakpoints. */
    columns?: string
    /** When true on a narrow viewport, show the detail pane instead of the list. */
    showDetail?: boolean
    /** Match the page's useMediaQuery('md') — when true, only one pane shows. */
    narrow?: boolean
    /** Kept for call-site compatibility; both tones are white. */
    surface?: 'canvas' | 'panel'
  }>(),
  {
    columns: 'minmax(0, min(380px, 40%)) minmax(0, 1fr)',
    showDetail: false,
    narrow: false,
    surface: 'canvas',
  },
)
</script>

<template>
  <div
    class="nudg-split nudg-master desk-split grid min-h-0 flex-1 overflow-hidden bg-white"
    :style="{ '--desk-split-cols': columns }"
  >
    <aside
      class="min-h-0 flex-col overflow-hidden border-r border-outline-gray-2 bg-white"
      :class="narrow && showDetail ? 'hidden' : 'flex'"
    >
      <slot name="master" />
    </aside>
    <main
      class="min-h-0 flex-col overflow-hidden bg-white"
      :class="narrow && !showDetail ? 'hidden' : 'flex'"
    >
      <slot name="detail" />
    </main>
  </div>
</template>

<style scoped>
.desk-split {
  grid-template-columns: minmax(0, 1fr);
}

@media (min-width: 768px) {
  .desk-split {
    grid-template-columns: var(--desk-split-cols);
  }
}
</style>
