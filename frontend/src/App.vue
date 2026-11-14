<script setup lang="ts">
import { onMounted } from 'vue'
import { FrappeUIProvider } from 'frappe-ui'
import AppShell from '@/components/AppShell.vue'
import { useDesk } from '@/stores/desk'

const desk = useDesk()
onMounted(() => {
  void desk.load()
})
</script>

<template>
  <FrappeUIProvider>
    <AppShell />
  </FrappeUIProvider>
</template>
