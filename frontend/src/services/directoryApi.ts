import { call } from 'frappe-ui'
import type { DirectoryAccess } from '@/utils/directoryAccess'

export interface DirectoryProfile {
  name: string
  profile_name: string
  phone_number: string
  whatsapp_account: string
  status: string
  created?: boolean
}

export interface DirectoryRecipient {
  mobile_number: string
  recipient_name: string
  unsubscribed: number
}

export interface DirectoryRecipientList {
  name: string
  list_name: string
  description: string
  whatsapp_account: string
  recipient_count: number
  recipients?: DirectoryRecipient[]
  created?: boolean
}

export function fetchDirectoryAccess() {
  return call<DirectoryAccess>('nudg.desk_api.directory_access')
}

export function listDirectoryProfiles(account?: string, query?: string) {
  return call<DirectoryProfile[]>('nudg.desk_api.list_directory_profiles', { account, query })
}

export function saveDirectoryProfile(payload: {
  name?: string
  profile_name?: string
  phone_number: string
  whatsapp_account: string
  status?: string
}) {
  return call<DirectoryProfile>('nudg.desk_api.save_directory_profile', payload)
}

export function deleteDirectoryProfile(name: string) {
  return call<{ name: string; deleted: boolean }>('nudg.desk_api.delete_directory_profile', { name })
}

export function listDirectoryRecipientLists(account?: string, query?: string) {
  return call<DirectoryRecipientList[]>('nudg.desk_api.list_directory_recipient_lists', { account, query })
}

export function getDirectoryRecipientList(name: string) {
  return call<DirectoryRecipientList>('nudg.desk_api.get_directory_recipient_list', { name })
}

export function saveDirectoryRecipientList(payload: {
  name?: string
  list_name: string
  description?: string
  whatsapp_account?: string
  recipients: DirectoryRecipient[]
}) {
  return call<DirectoryRecipientList>('nudg.desk_api.save_directory_recipient_list', payload)
}

export function deleteDirectoryRecipientList(name: string) {
  return call<{ name: string; deleted: boolean }>('nudg.desk_api.delete_directory_recipient_list', { name })
}
