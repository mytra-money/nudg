<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { headerKind, mediaFileName, mediaTypeLabel, publicMediaUrl } from '@/templatePreview'

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
      class="mb-1 max-h-40 w-full rounded-md object-cover"
      @error="failed = true"
    />

    <div
      v-else-if="kind === 'image' || kind === 'gif'"
      class="flex h-28 flex-col items-center justify-center rounded-md bg-[#d7efe0] px-3 text-center text-xs text-[#3d5348]"
    >
      <span class="font-medium">{{ kind === 'gif' ? 'GIF header' : 'Image header' }}</span>
      <span class="mt-1">No public example image is available.</span>
    </div>

    <div
      v-else-if="kind === 'video'"
      class="flex h-28 flex-col items-center justify-center rounded-md bg-[#1c1917] text-white"
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

    <div v-else-if="kind === 'document'" class="flex items-center gap-2 rounded-md bg-white/80 px-2 py-2">
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
