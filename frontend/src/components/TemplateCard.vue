<script setup lang="ts">
import { ref } from 'vue'
import { Button, TabButtons } from 'frappe-ui'
import DeskTemplatePreview from '@/components/DeskTemplatePreview.vue'
import type { Template } from '@/types'

const props = defineProps<{ template: Template }>()
defineEmits<{ use: [] }>()

const mode = ref<'preview' | 'raw'>('preview')
</script>

<template>
  <div class="space-y-3">
    <div>
      <p class="text-lg font-semibold">{{ template.template_label || template.name }}</p>
      <p class="mt-0.5 text-xs text-ink-gray-5">{{ template.template_name || template.name }}</p>
    </div>
    <dl class="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
      <div>
        <dt class="text-ink-gray-5">Category</dt>
        <dd class="text-ink-gray-9">{{ template.template_type }}</dd>
      </div>
      <div>
        <dt class="text-ink-gray-5">Language</dt>
        <dd class="text-ink-gray-9">{{ template.language }}</dd>
      </div>
      <div>
        <dt class="text-ink-gray-5">Status</dt>
        <dd class="text-ink-gray-9">{{ template.status }}</dd>
      </div>
      <div v-if="template.variable_format">
        <dt class="text-ink-gray-5">Variables</dt>
        <dd class="text-ink-gray-9">{{ template.variable_format }}</dd>
      </div>
    </dl>
    <TabButtons
      v-model="mode"
      :options="[
        { label: 'Preview', value: 'preview' },
        { label: 'Raw', value: 'raw' },
      ]"
    />
    <DeskTemplatePreview :template="template" :mode="mode" />
    <div class="flex flex-wrap gap-2">
      <Button variant="solid" label="Send to a profile" :disabled="template.status !== 'Approved'" @click="$emit('use')" />
    </div>
  </div>
</template>
