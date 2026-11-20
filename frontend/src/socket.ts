import { io, type Socket } from 'socket.io-client'
import { getCachedListResource, getCachedResource } from 'frappe-ui'

let socket: Socket | null = null

export function initSocket(): Socket {
  if (socket) return socket

  const socketioPort = window.socketio_port || 9000
  const host = window.location.hostname
  const siteName = window.site_name || window.sitename || host
  const port = window.location.port ? `:${socketioPort}` : ''
  const protocol = port ? 'http' : 'https'
  const url = `${protocol}://${host}${port}/${siteName}`

  // Avoid noisy reconnect loops in Vitest / offline sample mode.
  const enable = typeof window !== 'undefined' && Boolean(window.csrf_token) && import.meta.env.MODE !== 'test'

  socket = io(url, {
    withCredentials: true,
    autoConnect: enable,
    reconnection: enable,
    reconnectionDelay: 2000,
    reconnectionDelayMax: 30000,
    randomizationFactor: 0.5,
  })

  socket.on('refetch_resource', (data: { cache_key?: string }) => {
    if (!data?.cache_key) return
    const resource = getCachedResource(data.cache_key) || getCachedListResource(data.cache_key)
    resource?.reload()
  })

  return socket
}

export function getSocket(): Socket | null {
  return socket
}

/** Prefer Frappe's realtime bus. The local socket.io client covers the Nudg page boot. */
export function onDeskEvent(event: string, handler: (data: unknown) => void): boolean {
  const realtime = window.frappe?.realtime
  if (typeof realtime?.on === 'function') {
    realtime.on(event, handler)
    return true
  }
  const current = getSocket()
  if (!current) return false
  current.on(event, handler)
  return true
}
