<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Button, call } from 'frappe-ui'

const emit = defineEmits<{ connected: []; manual: [] }>()

type SignupConfig = {
  enabled: boolean
  ready: boolean
  app_id: string
  config_id: string
  graph_api_version: string
  has_secret: boolean
}

type SessionInfo = {
  waba_id: string
  phone_number_id: string
}

declare global {
  interface Window {
    FB?: {
      init: (options: Record<string, unknown>) => void
      login: (callback: (response: { authResponse?: { code?: string } }) => void, options: Record<string, unknown>) => void
    }
    fbAsyncInit?: () => void
  }
}

const config = ref<SignupConfig | null>(null)
const status = ref('')
const error = ref('')
const pin = ref('')
const busy = ref(false)

let sessionInfo: SessionInfo = { waba_id: '', phone_number_id: '' }
let pendingCode = ''
let finishing = false

onMounted(() => {
  window.addEventListener('message', onFacebookMessage)
  void loadConfig()
})

onUnmounted(() => {
  window.removeEventListener('message', onFacebookMessage)
})

async function loadConfig() {
  try {
    const res = (await call('nudg.desk_api.get_embedded_signup_config')) as SignupConfig
    config.value = res
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not load Embedded Signup settings.'
  }
}

function onFacebookMessage(event: MessageEvent) {
  if (event.origin !== 'https://www.facebook.com' && event.origin !== 'https://web.facebook.com') return
  let data: { type?: string; event?: string; data?: { waba_id?: string; phone_number_id?: string; error_message?: string } }
  try {
    data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data
  } catch {
    return
  }
  if (!data || data.type !== 'WA_EMBEDDED_SIGNUP') return
  const name = String(data.event || '').toUpperCase()
  if (data.data?.waba_id) {
    sessionInfo = {
      waba_id: String(data.data.waba_id),
      phone_number_id: data.data.phone_number_id ? String(data.data.phone_number_id) : '',
    }
  }
  if (name === 'CANCEL') {
    status.value = ''
    error.value = 'Signup was closed before it finished.'
    pendingCode = ''
    return
  }
  if (name === 'ERROR') {
    error.value = data.data?.error_message || 'Embedded Signup reported an error.'
    pendingCode = ''
    return
  }
  if (pendingCode) void finishSignup()
}

async function launchSignup() {
  error.value = ''
  pin.value = ''
  status.value = ''
  pendingCode = ''
  finishing = false
  sessionInfo = { waba_id: '', phone_number_id: '' }
  if (!config.value?.ready) {
    error.value = 'Save the App ID, configuration ID, and app secret first.'
    return
  }
  busy.value = true
  try {
    await loadFacebookSdk(config.value.app_id, config.value.graph_api_version)
    status.value = 'Finish the Facebook window. Do not close this page.'
    window.FB?.login(
      (response) => {
        const code = response?.authResponse?.code || ''
        if (!code) {
          busy.value = false
          error.value = 'Facebook did not return a signup code.'
          return
        }
        pendingCode = code
        void finishSignup()
      },
      {
        config_id: config.value.config_id,
        response_type: 'code',
        override_default_response_type: true,
        extras: {
          setup: {},
          sessionInfoVersion: '3',
        },
      },
    )
  } catch (err) {
    busy.value = false
    error.value = err instanceof Error ? err.message : 'Could not open Facebook login.'
  }
}

async function finishSignup() {
  if (!pendingCode || finishing) return
  finishing = true
  const started = Date.now()
  while (!sessionInfo.waba_id && Date.now() - started < 4000) {
    await new Promise((resolve) => window.setTimeout(resolve, 200))
  }
  try {
    const result = (await call('nudg.desk_api.complete_embedded_signup', {
      code: pendingCode,
      waba_id: sessionInfo.waba_id || undefined,
      phone_number_id: sessionInfo.phone_number_id || undefined,
    })) as { account_name?: string; pin?: string; warnings?: string[] }
    pin.value = result.pin || ''
    const warning = (result.warnings || []).filter(Boolean).join(' ')
    status.value = warning
      ? `Connected ${result.account_name}. ${warning}`
      : `Connected ${result.account_name}.`
    emit('connected')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Could not finish Embedded Signup.'
  } finally {
    pendingCode = ''
    finishing = false
    busy.value = false
  }
}

function loadFacebookSdk(app: string, version: string) {
  if (window.FB) {
    window.FB.init({ appId: app, autoLogAppEvents: true, xfbml: false, version })
    return Promise.resolve()
  }
  return new Promise<void>((resolve, reject) => {
    window.fbAsyncInit = () => {
      window.FB?.init({ appId: app, autoLogAppEvents: true, xfbml: false, version })
      resolve()
    }
    const script = document.createElement('script')
    script.async = true
    script.crossOrigin = 'anonymous'
    script.src = 'https://connect.facebook.net/en_US/sdk.js'
    script.onerror = () => reject(new Error('Could not load the Facebook SDK.'))
    document.body.appendChild(script)
  })
}
</script>

<template>
  <div>
    <div class="flex flex-wrap gap-2">
      <Button
        variant="solid"
        class="bg-[#1877F2] text-white hover:bg-[#166FE5]"
        :loading="busy"
        :disabled="!config?.ready"
        label="Login with Facebook"
        @click="launchSignup"
      />
      <Button variant="subtle" label="I already have credentials" @click="emit('manual')" />
    </div>
    <p v-if="config && !config.ready" class="mt-2 text-xs text-ink-gray-6">Facebook login is not available yet.</p>
    <p v-if="status" class="mt-2 text-xs text-emerald-800">{{ status }}</p>
    <p v-if="pin" class="mt-1 text-xs font-medium text-ink-gray-8">Two-step PIN: {{ pin }}. Save it. It is not shown again.</p>
    <p v-if="error" class="mt-2 text-xs text-red-700">{{ error }}</p>
  </div>
</template>
