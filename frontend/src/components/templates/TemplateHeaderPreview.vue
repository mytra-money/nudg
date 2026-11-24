<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { headerKind, mediaFileName, mediaTypeLabel, publicMediaUrl } from '@/utils/templatePreview'

const props = defineProps<{
  headerType?: string
  headerText?: string
  mediaUrl?: string
  mimeType?: string
}>()

const failed = ref(false)
watch(
  () => [props.mediaUrl, props.headerType],
  () => {
    failed.value = false
  },
)

const kind = computed(() => headerKind(props.headerType))
const src = computed(() => publicMediaUrl(props.mediaUrl))
const fileName = computed(() => mediaFileName(props.mediaUrl))
const typeLabel = computed(() => mediaTypeLabel(props.mimeType, fileName.value))
const showImage = computed(() => (kind.value === 'image' || kind.value === 'gif') && Boolean(src.value) && !failed.value)
const visible = computed(() => (kind.value === 'text' ? Boolean(props.headerText) : true))
</script>

<template>
  <div v-if="visible" class="mb-1.5">
    <p v-if="kind === 'text'" class="font-semibold">{{ headerText }}</p>

    <img
      v-else-if="showImage"
      :src="src || undefined"
      alt="Header image"
      class="-mx-2.5 -mt-2 mb-2 max-h-44 w-[calc(100%+1.25rem)] object-cover"
      @error="failed = true"
    />

    <div
      v-else-if="kind === 'image' || kind === 'gif'"
      class="-mx-2.5 -mt-2 mb-1.5 flex h-9 w-[calc(100%+1.25rem)] items-center gap-2 bg-[#e9edef] px-2.5 text-[11px] text-[#667781]"
    >
      <span class="grid size-6 shrink-0 place-items-center rounded bg-white text-[#54656f]" aria-hidden="true">
        <svg viewBox="0 0 24 24" class="size-3.5 fill-none stroke-current" stroke-width="1.8">
          <rect x="3.5" y="5" width="17" height="14" rx="2" />
          <circle cx="9" cy="10" r="1.4" />
          <path d="m7 16 3.2-3.2a1 1 0 0 1 1.4 0L16 17" />
        </svg>
      </span>
      <span class="shrink-0 font-medium text-[#111b21]">{{ kind === 'gif' ? 'GIF header' : 'Image header' }}</span>
      <span class="min-w-0 truncate">No public example image is available.</span>
    </div>

    <div
      v-else-if="kind === 'video'"
      class="-mx-2.5 -mt-2 mb-2 flex h-28 w-[calc(100%+1.25rem)] flex-col items-center justify-center bg-[#1c1917] text-white"
    >
      <span
        class="flex size-9 items-center justify-center rounded-full bg-white/15"
        aria-hidden="true"
      >
        <svg viewBox="0 0 24 24" class="ml-0.5 size-4 fill-current">
          <path d="M8 5.5v13l11-6.5-11-6.5z" />
        </svg>
      </span>
      <span class="mt-2 text-xs">Video header</span>
      <span v-if="mediaUrl" class="mt-0.5 max-w-full truncate px-3 text-[11px] text-white/70">{{ fileName }}</span>
    </div>

    <div v-else-if="kind === 'document'" class="flex items-center gap-2 rounded-md bg-[#f0f2f5] px-2 py-2">
      <span class="flex size-8 shrink-0 items-center justify-center rounded-md bg-[#d7efe0] text-[#1e3a32]" aria-hidden="true">
        <svg viewBox="0 0 24 24" class="size-4 fill-none stroke-current" stroke-width="1.8">
          <path d="M7 3.5h7l5 5V20a1.5 1.5 0 0 1-1.5 1.5h-10.5A1.5 1.5 0 0 1 5.5 20V5A1.5 1.5 0 0 1 7 3.5z" />
          <path d="M14 3.5V9h5.5" />
        </svg>
      </span>
      <span class="min-w-0">
        <span class="block truncate text-xs font-medium">{{ fileName }}</span>
        <span class="block text-[11px] text-[#66756b]">{{ typeLabel }}</span>
      </span>
    </div>

    <div v-else class="rounded-md bg-[#d7efe0] px-2.5 py-2 text-xs text-[#3d5348]">
      Unsupported header: {{ headerType }}
    </div>
  </div>
</template>
