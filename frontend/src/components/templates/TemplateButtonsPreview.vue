<script setup lang="ts">
import { fillVariables, type SampleSource } from '@/utils/templatePreview'
import type { TemplateButton } from '@/types'

const props = defineProps<{
  buttons?: TemplateButton[]
  samples: SampleSource
}>()

const KNOWN = new Set(['Quick Reply', 'URL', 'Phone Number', 'Copy Code', 'Voice Call'])

function filledUrl(url?: string) {
  return fillVariables(url, props.samples)
}
</script>

<template>
  <div
    v-if="buttons?.length"
    class="mt-1 overflow-hidden rounded-lg bg-white text-[#1e3a32] shadow-sm"
    role="group"
    aria-label="Template buttons, preview only"
  >
    <div
      v-for="(button, index) in buttons"
      :key="`${button.button_type}-${button.button_text}-${index}`"
      class="border-t border-[#e4eee8] px-3 py-2 text-center text-[13px] first:border-t-0"
      data-preview-button
    >
      <template v-if="KNOWN.has(button.button_type)">
        <span class="inline-flex items-center justify-center gap-1.5 font-medium">
          <svg v-if="button.button_type === 'Quick Reply'" viewBox="0 0 24 24" class="size-3.5 fill-none stroke-current" stroke-width="1.8" aria-hidden="true">
            <path d="M9 14 4 9l5-5" />
            <path d="M4 9h10a6 6 0 0 1 0 12h-3" />
          </svg>
          <svg v-else-if="button.button_type === 'URL'" viewBox="0 0 24 24" class="size-3.5 fill-none stroke-current" stroke-width="1.8" aria-hidden="true">
            <path d="M14 5h5v5" />
            <path d="M10 14 19 5" />
            <path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" />
          </svg>
          <svg v-else-if="button.button_type === 'Phone Number' || button.button_type === 'Voice Call'" viewBox="0 0 24 24" class="size-3.5 fill-none stroke-current" stroke-width="1.8" aria-hidden="true">
            <path d="M8 3.5h3l1.5 4-2 1.5a12 12 0 0 0 5 5l1.5-2 4 1.5v3A2 2 0 0 1 19.2 18 16 16 0 0 1 6 4.8 2 2 0 0 1 8 3.5z" />
          </svg>
          <svg v-else viewBox="0 0 24 24" class="size-3.5 fill-none stroke-current" stroke-width="1.8" aria-hidden="true">
            <rect x="8" y="8" width="12" height="12" rx="2" />
            <path d="M4 16V5a1 1 0 0 1 1-1h11" />
          </svg>
          {{ button.button_text }}
        </span>
        <span v-if="button.button_type === 'URL' && button.url" class="mt-0.5 block text-[11px] font-normal text-[#66756b]">
          {{ filledUrl(button.url) }}
        </span>
        <span v-else-if="button.button_type === 'Phone Number' && button.phone_number" class="mt-0.5 block text-[11px] font-normal text-[#66756b]">
          {{ button.phone_number }}
        </span>
        <span v-else-if="button.button_type === 'Voice Call'" class="mt-0.5 block text-[11px] font-normal text-[#66756b]">Voice call</span>
      </template>
      <span v-else>Unsupported button: {{ button.button_type || 'Unknown' }}</span>
    </div>
  </div>
</template>
