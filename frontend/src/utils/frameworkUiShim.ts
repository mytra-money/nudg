import { getSocket, initSocket } from '@/socket'

export function getSocketInstance() {
  return getSocket() || initSocket()
}

export function subscribeToDoc(_doctype?: string, _name?: string) {
  return () => {}
}
