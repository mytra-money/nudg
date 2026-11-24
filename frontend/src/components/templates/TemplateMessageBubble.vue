<script setup lang="ts">
import { computed } from 'vue'
import { formatWhatsAppMessage } from '@whatsapp/ui/utils/formatMessage'
import TemplateButtonsPreview from '@/components/templates/TemplateButtonsPreview.vue'
import TemplateHeaderPreview from '@/components/templates/TemplateHeaderPreview.vue'
import type { SampleSource } from '@/utils/templatePreview'
import type { TemplateButton } from '@/types'

const props = defineProps<{
  headerType?: string
  headerText?: string
  mediaUrl?: string
  mimeType?: string
  body?: string
  footer?: string
  buttons?: TemplateButton[]
  samples: SampleSource
  time: string
}>()

// Format each line on its own so a line break is a real element, not a tag
// glued to the front of the sanitized string.
const bodyLines = computed(() => (props.body || '').split('\n').map((line) => formatWhatsAppMessage(line)))
</script>

<template>
  <div class="flex w-full max-w-full flex-col items-start">
    <p class="mb-2 self-center rounded-full bg-white/90 px-2 py-0.5 text-center text-[10px] font-medium text-[#54656f] shadow-sm">
      Preview only. This message was not sent.
    </p>
    <div class="w-[min(100%,19.5rem)] overflow-hidden rounded-lg rounded-tl-sm bg-white text-[13.5px] leading-snug text-[#111b21] shadow-[0_1px_0.5px_rgba(11,20,26,0.13)]">
      <div class="px-2.5 py-2">
        <TemplateHeaderPreview
          :header-type="headerType"
          :header-text="headerText"
          :media-url="mediaUrl"
          :mime-type="mimeType"
        />
        <div v-if="body" class="wa-body break-words">
          <template v-for="(line, index) in bodyLines" :key="index">
            <br v-if="index" />
            <span v-if="line" v-html="line" />
          </template>
        </div>
        <p v-else-if="!headerText && headerType !== 'Image' && headerType !== 'Video' && headerType !== 'Document' && headerType !== 'GIF'" class="text-[#667781]">
          This template has no message text.
        </p>
        <div class="mt-1 flex items-end justify-between gap-3">
          <p v-if="footer" class="min-w-0 text-[11px] leading-snug text-[#667781]">{{ footer }}</p>
          <span v-else />
          <span class="shrink-0 text-[11px] leading-none text-[#667781]">{{ time }}</span>
        </div>
      </div>
    </div>
    <TemplateButtonsPreview class="w-[min(100%,19.5rem)]" :buttons="buttons" :samples="samples" />
  </div>
</template>

<style scoped>
.wa-body :deep(b) {
  font-weight: 600;
}
.wa-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
}
.wa-body :deep(li) {
  display: list-item;
  margin-left: 1rem;
}
</style>
