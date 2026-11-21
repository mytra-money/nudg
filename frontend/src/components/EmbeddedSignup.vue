<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Button, call, toast } from 'frappe-ui'
import { userFacingError } from '@/utils/errors'

const emit = defineEmits<{ connected: []; manual: [] }>()

type SignupConfig = {
  enabled: boolean
  ready: boolean
  app_id: string
  config_id: string
  graph_api_version: string
  has_secret: boolean
  missing?: string[]
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
let sessionEvent = ''
let pendingCode = ''
let finishing = false

onMounted(() => {
  window.addEventListener('message', onFacebookMessage)
  void loadConfig()
})

onUnmounted(() => {
  window.removeEventListener('message', onFacebookMessage)
})

const unavailableReason = computed(() => {
  const current = config.value
  if (!current || current.ready) return ''
  const missing = current.missing || []
  if (missing.length === 1 && missing[0] === 'app_secret') {
    return 'Type the Meta app secret again in WA Signup Settings and save.'
  }
  if (missing.includes('enabled')) {
    return 'Turn on WA Signup Settings, then open this dialog again.'
  }
  return 'Save the Meta App ID, configuration ID, and app secret in WA Signup Settings.'
})

async function loadConfig() {
  try {
    const res = (await call('nudg.desk_api.get_embedded_signup_config')) as SignupConfig
    config.value = res
  } catch (err) {
    error.value = userFacingError(err, 'Could not load Embedded Signup settings.')
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
  if (name) sessionEvent = name
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
    error.value = 'Facebook could not finish signup. Close the window and try again.'
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
  sessionEvent = ''
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
          featureType: 'whatsapp_business_app_onboarding',
          sessionInfoVersion: '3',
        },
      },
    )
  } catch (err) {
    busy.value = false
    error.value = userFacingError(err, 'Could not open Facebook login.')
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
      business_app: sessionEvent === 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING' ? 1 : 0,
    })) as { account_name?: string; pin?: string; warnings?: string[]; coexistence?: boolean }
    pin.value = result.coexistence ? '' : result.pin || ''
    const warning = (result.warnings || [])
      .map((item) => userFacingError(item, 'WhatsApp could not finish setup. Try connecting again.'))
      .find(Boolean)
    if (warning) {
      status.value = ''
      error.value = warning
      toast.error(warning)
    } else {
      status.value = result.coexistence
        ? `Connected ${result.account_name}. Chats from the WhatsApp Business app are copying in. This can take a few minutes.`
        : `Connected ${result.account_name}.`
      toast.success(status.value)
    }
    emit('connected')
  } catch (err) {
    error.value = userFacingError(err, 'Could not finish connecting WhatsApp.')
    toast.error(error.value)
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
    <div class="flex flex-col items-center gap-3">
      <Button
        variant="solid"
        class="w-full max-w-xs justify-center !bg-[#1877F2] !text-white hover:!bg-[#166FE5]"
        :loading="busy"
        :disabled="!config?.ready"
        label="Login with Facebook"
        @click="launchSignup"
      />
      <p class="max-w-xs text-center text-xs text-ink-gray-6">
        A number already on the WhatsApp Business app can stay on the phone. New Cloud API numbers are registered here.
      </p>
      <Button
        variant="solid"
        class="w-full max-w-xs justify-center !bg-[#e5e7eb] !text-[#111827] hover:!bg-[#d1d5db]"
        label="I already have credentials"
        @click="emit('manual')"
      />
    </div>
    <p v-if="unavailableReason" class="mt-3 text-center text-xs text-ink-gray-7">{{ unavailableReason }}</p>
    <p v-if="status" class="mt-3 text-center text-sm text-emerald-800">{{ status }}</p>
    <p v-if="pin" class="mt-1 text-center text-sm font-medium text-ink-gray-8">Two-step PIN: {{ pin }}. Save it. It is not shown again.</p>
    <div v-if="error" class="mx-auto mt-4 max-w-md rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-center" role="alert">
      <p class="text-sm font-semibold text-red-900">Error</p>
      <p class="mt-1 text-sm text-red-800">{{ error }}</p>
    </div>
  </div>
</template>
