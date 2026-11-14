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
  <div class="ml-auto flex w-[88%] max-w-full flex-col items-end">
    <div class="w-full rounded-lg rounded-tr-sm bg-[#e7f6df] px-2.5 py-2 text-[13px] leading-snug text-[#1c1917]">
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
      <p v-else-if="!headerText && headerType !== 'Image' && headerType !== 'Video' && headerType !== 'Document' && headerType !== 'GIF'" class="text-[#66756b]">
        This template has no message text.
      </p>
      <p v-if="footer" class="mt-1.5 text-[11px] leading-snug text-[#66756b]">{{ footer }}</p>
    </div>
    <TemplateButtonsPreview class="w-full" :buttons="buttons" :samples="samples" />
    <p class="mt-1 flex items-center gap-1 text-[11px] text-[#66756b]">
      <span>{{ time }}</span>
      <svg viewBox="0 0 24 14" class="h-3 w-4" aria-hidden="true">
        <path d="M1.5 7.2 5.2 11 12 3.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M7.5 7.2 11.2 11 18 3.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      <span class="sr-only">Preview only. This message was not sent.</span>
    </p>
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
