/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ROUTER_BASE?: string
}

interface Window {
  csrf_token?: string
  user?: string
  sitename?: string
  site_name?: string
  socketio_port?: number
  is_manager?: boolean
  is_system_manager?: boolean
  roles?: string[]
  frappe?: {
    session?: { user?: string }
    boot?: {
      user?: { roles?: string[]; name?: string; full_name?: string }
      user_info?: Record<string, { fullname?: string; full_name?: string; image?: string; email?: string }>
    }
    realtime?: {
      on?: (event: string, handler: (data: unknown) => void) => void
      off?: (event: string, handler: (data: unknown) => void) => void
    }
  }
  whatsapp_installed?: boolean
  __?: (message: string, replace?: unknown[], context?: string | null) => string
  integration?: {
    whatsapp_installed: boolean
    doctypes_ready: boolean
    missing_dependencies: string[]
    default_account: string | null
    active_account_count: number | null
    detail: string
  }
}
