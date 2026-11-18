import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { FrappeUI, frappeRequest, setConfig } from 'frappe-ui'
import App from './App.vue'
import { router } from './router'
import { initSocket } from './socket'
import translationPlugin from './translation'
import { createDialog } from './utils/dialogs'
import { purgeSharedDeskCache } from './utils/deskCache'
import './style.css'

purgeSharedDeskCache()

const pinia = createPinia()
const app = createApp(App)

setConfig('resourceFetcher', frappeRequest)

app.use(FrappeUI)
app.use(pinia)
app.use(router)
app.use(translationPlugin)

const socket = initSocket()
app.provide('$socket', socket)
app.config.globalProperties.$socket = socket
app.config.globalProperties.$dialog = createDialog

async function mountApp() {
  if (import.meta.env.DEV && !window.csrf_token) {
    try {
      const values = await frappeRequest({
        url: '/api/method/nudg.www.nudg.get_context_for_dev',
        method: 'GET',
      })
      if (values && typeof values === 'object') {
        for (const key of Object.keys(values as Record<string, unknown>)) {
          ;(window as unknown as Record<string, unknown>)[key] = (values as Record<string, unknown>)[key]
        }
      }
    } catch {
      // Sample mode when the site/dev boot endpoint is unavailable.
    }
  }
  app.mount('#app')
}

void mountApp()
