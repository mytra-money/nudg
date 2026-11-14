<script setup lang="ts">
import { Button } from 'frappe-ui'

defineProps<{
  title?: string
  message: string
  allowRetry?: boolean
}>()

const emit = defineEmits<{
  retry: []
}>()
</script>

<template>
  <div class="mx-auto max-w-lg rounded-xl border border-red-200 bg-red-50/50 p-6 my-8" role="alert" data-state="error">
    <div class="flex items-start gap-3">
      <div class="grid size-8 shrink-0 place-items-center rounded-lg bg-red-100 text-red-600">
        <span class="lucide-alert-circle size-4" aria-hidden="true" />
      </div>
      <div class="min-w-0 flex-1">
        <h2 class="text-sm font-semibold text-red-900">{{ title || 'Something went wrong' }}</h2>
        <p class="mt-1 text-xs leading-relaxed text-red-700">{{ message }}</p>
        <div v-if="allowRetry" class="mt-3">
          <Button
            variant="solid"
            size="sm"
            class="bg-red-600 text-white hover:bg-red-700"
            label="Try again"
            @click="emit('retry')"
          />
        </div>
      </div>
    </div>
  </div>
</template>
