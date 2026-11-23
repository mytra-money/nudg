<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Badge, Button, Dialog, FormControl, Select, TextInput, dialog, toast } from 'frappe-ui'
import { NumberCard } from 'frappe-ui/charts'
import DeskCard from '@/components/desk/DeskCard.vue'
import DeskEmpty from '@/components/desk/DeskEmpty.vue'
import DeskPage from '@/components/desk/DeskPage.vue'
import DeskSplit from '@/components/desk/DeskSplit.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { errorText } from '@/utils/format'
import { accountArg } from '@/utils/accountSelection'
import { useDesk } from '@/stores/desk'
import {
  createCatalog,
  createCatalogItem,
  deleteCatalog,
  deleteCatalogItem,
  listCatalogItems,
  listCatalogs,
  sendCatalogProduct,
  syncCatalog,
  updateCatalog,
  updateCatalogItem,
} from '@/services/catalogApi'

const desk = useDesk()

const loading = ref(true)
const error = ref<string | null>(null)
const catalogs = ref<any[]>([])
const items = ref<any[]>([])
const selectedCatalogName = ref<string | null>(null)
const busy = ref(false)
const searchQuery = ref('')
const itemSearchQuery = ref('')
const itemStatusFilter = ref<'all' | 'Active' | 'Inactive'>('all')

// Interactive SPM Modal State
const showSendModal = ref(false)
const selectedItemToSend = ref<any | null>(null)
const recipientProfile = ref('')
const customBodyText = ref('')
const customFooterText = ref('Tap below to view details in WhatsApp')
const isSendingProduct = ref(false)

// Sample Demo Data Fallbacks
const sampleCatalogs: any[] = [
  {
    name: 'CAT-SPICE-01',
    catalog_name: 'Sundarban Signature Spices',
    whatsapp_account: 'Sundarban Sales',
    status: 'Active',
    meta_catalog_id: 'meta_cat_8829104812',
    sync_status: 'Error',
    sync_error:
      'Meta Commerce Catalog sync is not enabled in this build. Catalog data is stored on this site only.',
    description: 'Single-origin spices, hand-harvested green cardamom, Tellicherry pepper, and saffron from organic reserves.',
    modified: new Date(Date.now() - 3600_000 * 2).toISOString(),
  },
  {
    name: 'CAT-GIFT-02',
    catalog_name: 'Festive Hampers & Spice Trunks',
    whatsapp_account: 'Sundarban Dispatch',
    status: 'Active',
    meta_catalog_id: 'meta_cat_9931849102',
    sync_status: 'Error',
    sync_error:
      'Meta Commerce Catalog sync is not enabled in this build. Catalog data is stored on this site only.',
    description: 'Curated wooden gift boxes, handcrafted brass spice boxes, and festive corporate allocations.',
    modified: new Date(Date.now() - 3600_000 * 24).toISOString(),
  },
]

const sampleItemsByCatalog: Record<string, any[]> = {
  'CAT-SPICE-01': [
    {
      name: 'ITEM-001',
      catalog: 'CAT-SPICE-01',
      item_name: 'Royal Green Cardamom (500g)',
      sku: 'SPI-CRD-01',
      description: 'Extra-bold 8mm green cardamom pods, shade-dried to lock in essential oils and pungent aroma.',
      price: 850,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_crd_01',
      status: 'Active',
      sort_order: 1,
    },
    {
      name: 'ITEM-002',
      catalog: 'CAT-SPICE-01',
      item_name: 'Tellicherry Black Pepper (250g)',
      sku: 'SPI-PEP-02',
      description: 'Sun-dried jumbo Tellicherry peppercorns from ancient vines with rich heat and citrus undertones.',
      price: 420,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_pep_02',
      status: 'Active',
      sort_order: 2,
    },
    {
      name: 'ITEM-003',
      catalog: 'CAT-SPICE-01',
      item_name: 'Organic Kashmiri Mongra Saffron (1g)',
      sku: 'SPI-SAF-03',
      description: 'Grade-A pure red stigma threads with intense floral aroma and natural crimson color release.',
      price: 650,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_saf_03',
      status: 'Active',
      sort_order: 3,
    },
    {
      name: 'ITEM-004',
      catalog: 'CAT-SPICE-01',
      item_name: 'Ceylon Sweet Cinnamon Quills (200g)',
      sku: 'SPI-CIN-04',
      description: 'Delicate paper-thin layered true cinnamon quills with soft floral sweetness and zero bitter cassia.',
      price: 310,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_cin_04',
      status: 'Active',
      sort_order: 4,
    },
  ],
  'CAT-GIFT-02': [
    {
      name: 'ITEM-005',
      catalog: 'CAT-GIFT-02',
      item_name: 'Artisanal Spice Trunk (6 Jars Assortment)',
      sku: 'GFT-TRK-01',
      description: 'Handcrafted teak wood chest holding 6 signature reserve whole spices with brass spoon.',
      price: 2400,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_trk_01',
      status: 'Active',
      sort_order: 1,
    },
    {
      name: 'ITEM-006',
      catalog: 'CAT-GIFT-02',
      item_name: 'Heritage Brass Spice Dabba (7 Compartments)',
      sku: 'GFT-DBA-02',
      description: 'Traditional heavy-gauge hammered brass masala box with airtight lid and master measure.',
      price: 1750,
      currency: 'INR',
      image: '',
      meta_retailer_id: 'ret_dba_02',
      status: 'Active',
      sort_order: 2,
    },
  ],
}

function showToast(message: string, isError = false) {
  if (isError) {
    toast.error(message)
  } else {
    toast.success(message)
  }
}

const catalogEditorOpen = ref(false)
const catalogEditorMode = ref<'create' | 'edit'>('create')
const editingCatalogName = ref('')
const catalogForm = ref({ catalog_name: '', whatsapp_account: '', description: '', status: 'Draft' })
const itemEditorOpen = ref(false)
const itemEditorMode = ref<'create' | 'edit'>('create')
const editingItemName = ref('')
const itemForm = ref({ item_name: '', sku: '', description: '', price: '', currency: 'INR', status: 'Active', image: '' })
const savingCatalog = ref(false)

const currentAccount = computed(() => accountArg(desk.account.value) || '')

/** Demo-mode helper: keep rows that belong to the selected number. */
function forAccount<T extends { whatsapp_account?: string }>(rows: T[]): T[] {
  const account = currentAccount.value
  if (!account) return rows
  return rows.filter((row) => !row.whatsapp_account || row.whatsapp_account === account)
}

function startCatalog(existing?: any) {
  catalogEditorMode.value = existing ? 'edit' : 'create'
  editingCatalogName.value = existing?.name || ''
  catalogForm.value = {
    catalog_name: existing?.catalog_name || '',
    whatsapp_account: currentAccount.value || existing?.whatsapp_account || '',
    description: existing?.description || '',
    status: existing?.status || 'Draft',
  }
  catalogEditorOpen.value = true
}

function startItem(existing?: any) {
  if (!selectedCatalogName.value && !existing) {
    showToast('Choose a catalog first.')
    return
  }
  itemEditorMode.value = existing ? 'edit' : 'create'
  editingItemName.value = existing?.name || ''
  itemForm.value = {
    item_name: existing?.item_name || '',
    sku: existing?.sku || '',
    description: existing?.description || '',
    price: existing?.price != null ? String(existing.price) : '',
    currency: existing?.currency || 'INR',
    status: existing?.status || 'Active',
    image: existing?.image || '',
  }
  itemEditorOpen.value = true
}

async function saveCatalogForm() {
  const catalogName = catalogForm.value.catalog_name.trim()
  if (!catalogName) {
    showToast('Catalog name is required.', true)
    return
  }
  savingCatalog.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      if (catalogEditorMode.value === 'edit') {
        const index = catalogs.value.findIndex((row) => row.name === editingCatalogName.value)
        if (index >= 0) {
          catalogs.value[index] = {
            ...catalogs.value[index],
            name: catalogName,
            catalog_name: catalogName,
            whatsapp_account: catalogForm.value.whatsapp_account,
            description: catalogForm.value.description.trim(),
            status: catalogForm.value.status,
          }
        }
        selectedCatalogName.value = catalogName
      } else {
        catalogs.value = [
          {
            name: catalogName,
            catalog_name: catalogName,
            whatsapp_account: catalogForm.value.whatsapp_account,
            description: catalogForm.value.description.trim(),
            status: catalogForm.value.status,
            sync_status: 'Not Synced',
          },
          ...catalogs.value,
        ]
        selectedCatalogName.value = catalogName
        items.value = []
      }
      catalogEditorOpen.value = false
      showToast(catalogEditorMode.value === 'edit' ? 'Catalog updated' : 'Catalog created')
      return
    }
    const saved =
      catalogEditorMode.value === 'edit'
        ? await updateCatalog({
            name: editingCatalogName.value,
            catalog_name: catalogName,
            whatsapp_account: catalogForm.value.whatsapp_account || undefined,
            description: catalogForm.value.description.trim(),
            status: catalogForm.value.status,
          })
        : await createCatalog({
            catalog_name: catalogName,
            whatsapp_account: catalogForm.value.whatsapp_account || undefined,
            description: catalogForm.value.description.trim(),
            status: catalogForm.value.status,
          })
    catalogEditorOpen.value = false
    showToast(catalogEditorMode.value === 'edit' ? 'Catalog updated' : 'Catalog created')
    selectedCatalogName.value = saved?.name || catalogName
    await load()
  } catch (caught) {
    showToast(errorText(caught), true)
  } finally {
    savingCatalog.value = false
  }
}

function removeCatalog() {
  if (catalogEditorMode.value !== 'edit' || !editingCatalogName.value) return
  const name = editingCatalogName.value
  const label = catalogForm.value.catalog_name || name
  dialog.danger({
    title: 'Delete catalog?',
    message: `Remove “${label}” and its items from Nudg?`,
    onConfirm: async () => {
      savingCatalog.value = true
      const isLive = Boolean(window.csrf_token)
      try {
        if (isLive) await deleteCatalog(name)
        catalogs.value = catalogs.value.filter((row) => row.name !== name)
        if (selectedCatalogName.value === name) {
          selectedCatalogName.value = catalogs.value[0]?.name || null
          items.value = []
        }
        catalogEditorOpen.value = false
        showToast('Catalog deleted')
      } finally {
        savingCatalog.value = false
      }
    },
  })
}

function removeItem() {
  if (itemEditorMode.value !== 'edit' || !editingItemName.value) return
  const name = editingItemName.value
  const label = itemForm.value.item_name || name
  dialog.danger({
    title: 'Delete item?',
    message: `Remove “${label}” from this catalog?`,
    onConfirm: async () => {
      savingCatalog.value = true
      const isLive = Boolean(window.csrf_token)
      try {
        if (isLive) await deleteCatalogItem(name)
        items.value = items.value.filter((row) => row.name !== name)
        itemEditorOpen.value = false
        showToast('Item deleted')
      } finally {
        savingCatalog.value = false
      }
    },
  })
}

async function saveItemForm() {
  const itemName = itemForm.value.item_name.trim()
  if (!itemName) {
    showToast('Item name is required.', true)
    return
  }
  const catalogName = selectedCatalogName.value
  if (!catalogName) {
    showToast('Choose a catalog first.', true)
    return
  }
  savingCatalog.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      const row = {
        name: itemEditorMode.value === 'edit' ? editingItemName.value : `item-${Date.now()}`,
        catalog: catalogName,
        item_name: itemName,
        sku: itemForm.value.sku.trim(),
        description: itemForm.value.description.trim(),
        price: Number(itemForm.value.price || 0),
        currency: itemForm.value.currency || 'INR',
        status: itemForm.value.status,
        image: itemForm.value.image.trim(),
      }
      const bucket = sampleItemsByCatalog[catalogName] || (sampleItemsByCatalog[catalogName] = [])
      if (itemEditorMode.value === 'edit') {
        const index = bucket.findIndex((item) => item.name === editingItemName.value)
        if (index >= 0) bucket[index] = { ...bucket[index], ...row }
      } else {
        bucket.unshift(row)
      }
      items.value = [...bucket]
      itemEditorOpen.value = false
      showToast(itemEditorMode.value === 'edit' ? 'Item updated' : 'Item added')
      return
    }
    if (itemEditorMode.value === 'edit') {
      await updateCatalogItem({
        name: editingItemName.value,
        item_name: itemName,
        sku: itemForm.value.sku.trim(),
        description: itemForm.value.description.trim(),
        price: itemForm.value.price,
        currency: itemForm.value.currency,
        status: itemForm.value.status,
        image: itemForm.value.image.trim(),
      })
    } else {
      await createCatalogItem({
        catalog: catalogName,
        item_name: itemName,
        sku: itemForm.value.sku.trim(),
        description: itemForm.value.description.trim(),
        price: itemForm.value.price,
        currency: itemForm.value.currency,
        status: itemForm.value.status,
        image: itemForm.value.image.trim(),
      })
    }
    itemEditorOpen.value = false
    showToast(itemEditorMode.value === 'edit' ? 'Item updated' : 'Item added')
    await open(catalogName)
  } catch (caught) {
    showToast(errorText(caught), true)
  } finally {
    savingCatalog.value = false
  }
}

function ensureSelection() {
  const stillThere = catalogs.value.some((c) => c.name === selectedCatalogName.value)
  if (!stillThere) selectedCatalogName.value = catalogs.value[0]?.name || null
}

function loadSample() {
  catalogs.value = forAccount(sampleCatalogs)
  ensureSelection()
  items.value = selectedCatalogName.value ? sampleItemsByCatalog[selectedCatalogName.value] || [] : []
}

async function load() {
  loading.value = true
  error.value = null
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      loadSample()
      return
    }
    const result = await listCatalogs(currentAccount.value || undefined)
    catalogs.value = result || []
    ensureSelection()
    if (selectedCatalogName.value) {
      await open(selectedCatalogName.value)
    } else {
      items.value = []
    }
  } catch (caught) {
    if (!isLive) {
      loadSample()
    } else {
      error.value = errorText(caught)
    }
  } finally {
    loading.value = false
  }
}

async function open(name: string) {
  selectedCatalogName.value = name
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      items.value = sampleItemsByCatalog[name] || []
      return
    }
    const result = await listCatalogItems(name)
    items.value = result || []
  } catch (caught) {
    if (!isLive) {
      items.value = sampleItemsByCatalog[name] || []
    } else {
      showToast(errorText(caught))
    }
  }
}

async function sync(name: string) {
  busy.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      const target = catalogs.value.find((c) => c.name === name)
      const message =
        'Meta Commerce Catalog sync is not enabled in this build. Catalog data is stored on this site only.'
      if (target) {
        target.sync_status = 'Error'
        target.sync_error = message
      }
      showToast(message, true)
      return
    }
    const result = await syncCatalog(name)
    if (result.sync_error || result.sync_status === 'Error') {
      showToast(result.sync_error || 'Catalog sync is not available.', true)
    } else {
      showToast(result.sync_status || 'Sync requested successfully.')
    }
    await load()
    if (selectedCatalogName.value === name) await open(name)
  } catch (caught) {
    showToast(errorText(caught))
  } finally {
    busy.value = false
  }
}

function openSendModal(item: any) {
  selectedItemToSend.value = item
  customBodyText.value = `Hello! Check out our ${item.item_name}. It's in stock and ready to ship:`
  const defaultConv = desk.inbox.value?.conversations?.[0]
  recipientProfile.value = defaultConv?.profile.name || ''
  showSendModal.value = true
}

async function handleSendProduct() {
  if (!selectedItemToSend.value || !recipientProfile.value) {
    showToast('Please select a recipient to send this product message to.')
    return
  }
  isSendingProduct.value = true
  const isLive = Boolean(window.csrf_token)
  try {
    if (!isLive) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      showToast(`Product "${selectedItemToSend.value.item_name}" sent to customer!`)
      showSendModal.value = false
      return
    }
    await sendCatalogProduct({
      profile: recipientProfile.value,
      item: selectedItemToSend.value.name,
      body_text: customBodyText.value,
      footer_text: customFooterText.value,
    })
    showToast(`Single-Product Message dispatched successfully!`)
    showSendModal.value = false
  } catch (caught) {
    showToast(errorText(caught))
  } finally {
    isSendingProduct.value = false
  }
}

const selectedCatalog = computed(() => {
  return catalogs.value.find((c) => c.name === selectedCatalogName.value) || null
})

const syncStatusLabel = computed(() => selectedCatalog.value?.sync_status || 'Not synced')
const syncStatusDetail = computed(() => {
  if (selectedCatalog.value?.sync_error) return selectedCatalog.value.sync_error
  return 'Catalog data is stored on this site. Meta catalog import is not available.'
})

const filteredCatalogs = computed(() => {
  if (!searchQuery.value) return catalogs.value
  const query = searchQuery.value.toLowerCase()
  return catalogs.value.filter(
    (c) =>
      c.catalog_name?.toLowerCase().includes(query) ||
      c.name?.toLowerCase().includes(query) ||
      c.whatsapp_account?.toLowerCase().includes(query),
  )
})

const filteredItems = computed(() => {
  return items.value.filter((item) => {
    const matchesSearch =
      !itemSearchQuery.value ||
      item.item_name?.toLowerCase().includes(itemSearchQuery.value.toLowerCase()) ||
      item.sku?.toLowerCase().includes(itemSearchQuery.value.toLowerCase())
    if (!matchesSearch) return false

    if (itemStatusFilter.value === 'all') return true
    return item.status === itemStatusFilter.value
  })
})

const totalProductsCount = computed(() => {
  return items.value.length
})

const activeProductsCount = computed(() => items.value.filter((item) => item.status === 'Active').length)
const syncedCatalogsCount = computed(() => catalogs.value.filter((c) => c.sync_status === 'Synced').length)

const catalogStatusOptions = [
  { label: 'Draft', value: 'Draft' },
  { label: 'Active', value: 'Active' },
  { label: 'Archived', value: 'Archived' },
]
const itemStatusOptions = [
  { label: 'Active', value: 'Active' },
  { label: 'Inactive', value: 'Inactive' },
]
const itemStatusFilterOptions = computed(() => [
  { label: `All (${items.value.length})`, value: 'all' },
  { label: 'Active', value: 'Active' },
  { label: 'Inactive', value: 'Inactive' },
])
const recipientOptions = computed(() => [
  { label: 'Select customer...', value: '' },
  ...(desk.inbox.value?.conversations || []).map((conv: any) => ({
    label: `${conv.profile.profile_name || conv.profile.name} (${conv.profile.phone_number})`,
    value: conv.profile.name,
  })),
])

function formatCurrency(price?: number, currency = 'INR') {
  if (price === undefined || price === null) return ''
  if (currency === 'INR') {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(price)
  }
  return `${currency} ${price.toFixed(2)}`
}

onMounted(() => {
  desk.load()
  load()
})

watch(
  () => desk.account.value,
  () => void load(),
)
</script>

<template>
  <DeskPage variant="scroll">
    <template #badges>
      <Badge label="Stored on this site" theme="amber" variant="subtle" size="md" />
    </template>

    <template #actions>
      <Button variant="subtle" icon-left="lucide-refresh-cw" label="Refresh" :loading="loading" @click="load" />
      <Button variant="subtle" icon-left="lucide-plus" label="New Catalog" @click="startCatalog()" />
      <Button
        variant="solid"
        class="bg-[#075E54] text-white hover:bg-[#128C7E]"
        icon-left="lucide-plus"
        label="Add Catalog Item"
        @click="startItem()"
      />
    </template>

    <template #kpi>
      <div class="grid grid-cols-1 items-stretch gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <NumberCard
          title="Catalogs"
          :value="catalogs.length"
          color="#075E54"
          :delta-caption="selectedCatalog ? 'Selected: ' + selectedCatalog.catalog_name : 'No catalog selected'"
        />
        <NumberCard
          title="Products"
          :value="totalProductsCount"
          color="#047857"
          delta-caption="In the catalog selected on the left"
        />
        <NumberCard
          title="Active products"
          :value="activeProductsCount"
          :target="totalProductsCount"
          color="#1D4ED8"
          delta-caption="Send one product from a conversation"
        />
        <NumberCard
          title="Synced catalogs"
          :value="syncedCatalogsCount"
          :target="catalogs.length"
          :color="syncStatusLabel === 'Error' ? '#B91C1C' : '#B45309'"
          :delta-caption="'Selected: ' + syncStatusLabel"
        />
      </div>
    </template>

    <!-- State Containers (Loading / Error / Empty) -->
    <DeskEmpty v-if="loading" kind="loading" title="Loading product catalogs…" />
    <DeskEmpty v-else-if="error" kind="error" :message="error" allow-retry @retry="load" />
    <DeskEmpty
      v-else-if="!catalogs.length"
      title="No catalogs yet"
      description="Create a catalog on this site, then send its products from a conversation."
    />

    <!-- Master-Detail Layout -->
    <DeskSplit
      v-else
      surface="panel"
      columns="minmax(16rem, 20rem) minmax(0, 1fr)"
      class="min-h-[32rem] rounded-xl border border-outline-gray-2"
    >
      <template #master>
        <div class="border-b border-outline-gray-2 p-4">
          <div class="flex h-9 items-center justify-between gap-3">
            <h2 class="text-sm font-semibold text-ink-gray-9">Collections ({{ catalogs.length }})</h2>
            <Button variant="ghost" size="sm" label="New" @click="startCatalog()" />
          </div>
          <TextInput v-model="searchQuery" class="mt-3 w-full" placeholder="Search collections...">
            <template #prefix>
              <span class="lucide-search size-3.5 text-ink-gray-4" />
            </template>
          </TextInput>
        </div>

        <div class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2">
          <DeskCard
            v-for="cat in filteredCatalogs"
            :key="cat.name"
            as="button"
            interactive
            :padding="false"
            class="flex flex-col gap-1.5 px-4 py-3"
            :class="selectedCatalogName === cat.name ? '!border-[#128C7E] !bg-[#075E54]/5' : ''"
            @click="open(cat.name)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="min-w-0 truncate text-sm font-semibold text-ink-gray-9">{{ cat.catalog_name }}</span>
              <StatusBadge :label="cat.sync_status || 'Pending'" />
            </div>
            <p class="line-clamp-2 text-xs leading-5 text-ink-gray-6">{{ cat.description || 'No catalog description provided.' }}</p>
            <div class="flex items-center justify-between gap-3 text-[11px] text-ink-gray-5">
              <span class="min-w-0 truncate">{{ cat.whatsapp_account || 'No account' }}</span>
              <span class="shrink-0 font-mono">{{ cat.name }}</span>
            </div>
          </DeskCard>
        </div>
      </template>
      <template #detail>
        <!-- Detail Column: Catalog Products & Actions -->
        <div v-if="selectedCatalog" class="flex min-w-0 flex-1 flex-col overflow-y-auto p-4 sm:p-5">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="min-w-0 truncate text-lg font-bold text-ink-gray-9">{{ selectedCatalog.catalog_name }}</h2>
            <StatusBadge :label="selectedCatalog.status || 'Inactive'" />
          </div>
          <p class="mt-1 text-xs leading-5 text-ink-gray-6">{{ selectedCatalog.description || 'No description' }}</p>
          <p v-if="selectedCatalog.sync_error" class="mt-2 text-sm text-red-700" role="alert">
            {{ selectedCatalog.sync_error }}
          </p>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <Badge :label="'Meta ID ' + (selectedCatalog.meta_catalog_id || 'Not set')" theme="gray" variant="subtle" size="md" />
            <Badge :label="selectedCatalog.whatsapp_account || 'No account'" theme="gray" variant="subtle" size="md" />
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2 border-b border-outline-gray-2 pb-4">
            <Button
              variant="subtle"
              icon-left="lucide-refresh-cw"
              :label="busy ? 'Syncing...' : 'Sync catalog'"
              :loading="busy"
              @click="sync(selectedCatalog.name)"
            />
            <Button variant="subtle" label="Edit catalog" @click="startCatalog(selectedCatalog)" />
            <Button
              variant="solid"
              class="bg-[#075E54] text-white hover:bg-[#128C7E]"
              icon-left="lucide-plus"
              label="New Item"
              @click="startItem()"
            />
          </div>

          <!-- Items Filter & Search -->
          <div class="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <TextInput
              v-model="itemSearchQuery"
              class="w-full sm:max-w-xs sm:flex-1"
              placeholder="Search products or SKU..."
            >
              <template #prefix>
                <span class="lucide-search size-3.5 text-ink-gray-4" />
              </template>
            </TextInput>
            <Select
              class="w-full sm:w-40"
              :model-value="itemStatusFilter"
              :options="itemStatusFilterOptions"
              @update:model-value="(val) => (itemStatusFilter = (String(val || 'all') as typeof itemStatusFilter))"
            />
          </div>

          <div v-if="filteredItems.length > 0" class="mt-4 space-y-3">
            <DeskCard
              v-for="item in filteredItems"
              :key="item.name"
              as="article"
              class="!p-4"
            >
              <div class="flex items-start gap-3">
                <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[#25D366]/20 bg-[#25D366]/10 text-[#075E54]">
                  <span class="lucide-package size-5" />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-start justify-between gap-3">
                    <h3 class="min-w-0 truncate text-sm font-semibold text-ink-gray-9">{{ item.item_name }}</h3>
                    <span class="shrink-0 text-sm font-semibold tabular-nums text-emerald-700">
                      {{ formatCurrency(item.price, item.currency) }}
                    </span>
                  </div>
                  <div class="mt-1 flex flex-wrap items-center gap-2">
                    <Badge :label="item.sku || 'No SKU'" theme="gray" variant="subtle" size="sm" />
                    <Badge
                      :variant="item.status === 'Active' ? 'subtle' : 'outline'"
                      :theme="item.status === 'Active' ? 'green' : 'gray'"
                      size="sm"
                    >
                      {{ item.status }}
                    </Badge>
                  </div>
                  <p class="mt-2 line-clamp-2 text-xs leading-5 text-ink-gray-6">
                    {{ item.description || 'No product description provided.' }}
                  </p>
                </div>
              </div>
              <div class="mt-3 flex items-center justify-end gap-2 border-t border-outline-gray-1 pt-3">
                <Button variant="subtle" size="sm" icon-left="lucide-pencil" label="Edit" @click="startItem(item)" />
                <Button
                  variant="solid"
                  size="sm"
                  class="bg-[#075E54] text-white hover:bg-[#128C7E]"
                  icon-left="lucide-send"
                  label="Send to Customer"
                  @click="openSendModal(item)"
                />
              </div>
            </DeskCard>
          </div>

          <!-- Empty Items State -->
          <div
            v-else
            class="mt-6 flex flex-col items-center justify-center rounded-xl border border-dashed border-outline-gray-2 bg-white p-10 text-center"
          >
            <div class="flex h-10 w-10 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-5">
              <span class="lucide-package size-5" />
            </div>
            <h3 class="mt-2 text-sm font-semibold text-ink-gray-9">No Product Items in Collection</h3>
            <p class="mt-1 text-xs text-ink-gray-5">Add WA Catalog Item records to display products in this catalog.</p>
            <Button
              class="mt-3 bg-[#075E54] text-white hover:bg-[#128C7E]"
              variant="solid"
              icon-left="lucide-plus"
              label="Add Catalog Item"
              @click="startItem()"
            />
          </div>
        </div>
      </template>
    </DeskSplit>

    <Dialog v-model="catalogEditorOpen" :title="catalogEditorMode === 'edit' ? 'Edit catalog' : 'New catalog'">
      <div class="space-y-3 py-1">
        <FormControl v-model="catalogForm.catalog_name" type="text" label="Catalog name" />
        <FormControl v-model="catalogForm.description" type="textarea" label="Description" :rows="3" />
        <FormControl v-model="catalogForm.status" type="select" label="Status" :options="catalogStatusOptions" />
      </div>
      <template #actions>
        <div class="flex w-full items-center justify-between gap-2">
          <Button v-if="catalogEditorMode === 'edit'" label="Delete" :loading="savingCatalog" @click="removeCatalog" />
          <span v-else />
          <div class="flex gap-2">
            <Button label="Cancel" @click="catalogEditorOpen = false" />
            <Button variant="solid" class="bg-[#075E54] text-white" :label="catalogEditorMode === 'edit' ? 'Save' : 'Create catalog'" :loading="savingCatalog" @click="saveCatalogForm" />
          </div>
        </div>
      </template>
    </Dialog>

    <Dialog v-model="itemEditorOpen" :title="itemEditorMode === 'edit' ? 'Edit item' : 'New catalog item'">
      <div class="space-y-3 py-1">
        <FormControl v-model="itemForm.item_name" type="text" label="Item name" />
        <FormControl v-model="itemForm.sku" type="text" label="SKU" />
        <FormControl v-model="itemForm.description" type="textarea" label="Description" :rows="3" />
        <div class="grid grid-cols-2 gap-3">
          <FormControl v-model="itemForm.price" type="number" label="Price" min="0" step="0.01" />
          <FormControl v-model="itemForm.currency" type="text" label="Currency" />
        </div>
        <FormControl v-model="itemForm.image" type="text" label="Image" placeholder="https://… or /files/…" />
        <FormControl v-model="itemForm.status" type="select" label="Status" :options="itemStatusOptions" />
      </div>
      <template #actions>
        <div class="flex w-full items-center justify-between gap-2">
          <Button v-if="itemEditorMode === 'edit'" label="Delete" :loading="savingCatalog" @click="removeItem" />
          <span v-else />
          <div class="flex gap-2">
            <Button label="Cancel" @click="itemEditorOpen = false" />
            <Button variant="solid" class="bg-[#075E54] text-white" :label="itemEditorMode === 'edit' ? 'Save' : 'Add item'" :loading="savingCatalog" @click="saveItemForm" />
          </div>
        </div>
      </template>
    </Dialog>

    <!-- MODAL: Send Single-Product Message (SPM) with Live WhatsApp Preview -->
    <Dialog
      v-model="showSendModal"
      title="Send Single-Product Message (SPM)"
      size="2xl"
    >
      <div v-if="selectedItemToSend" class="space-y-4 py-1">
        <p class="text-xs text-ink-gray-6 -mt-2">
          Dispatch an interactive Meta WhatsApp product card directly to a customer thread
        </p>

        <div class="mt-3 grid items-start gap-6 md:grid-cols-2">
          <!-- Configuration Form -->
          <div class="space-y-4">
            <FormControl
              v-model="recipientProfile"
              type="select"
              label="Target Customer / Thread"
              :options="recipientOptions"
            />
            <FormControl
              v-model="customBodyText"
              type="textarea"
              label="Message Body"
              :rows="3"
              placeholder="Enter introductory message text..."
            />
            <FormControl
              v-model="customFooterText"
              type="text"
              label="Footer Note"
              placeholder="Tap below to view details"
            />
          </div>

          <!-- Live WhatsApp Chat Bubble Preview -->
          <div class="flex flex-col rounded-xl bg-[#efeae2]/40 p-4 ring-1 ring-black/5">
            <span class="mb-2 text-center text-[10px] font-semibold text-ink-gray-5 uppercase tracking-wider">
              Customer Chat Preview
            </span>

            <div class="rounded-xl border border-[#d1d7db] bg-white p-3.5 shadow-sm">
              <p class="text-xs text-ink-gray-9 leading-relaxed whitespace-pre-wrap">{{ customBodyText }}</p>

              <!-- Interactive SPM Product Card -->
              <div class="mt-2.5 overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-2/40">
                <div class="flex h-24 items-center justify-center bg-gradient-to-br from-emerald-100 to-teal-50 text-[#075E54]">
                  <span class="lucide-shopping-bag size-9 text-[#075E54]" />
                </div>
                <div class="p-2.5">
                  <h4 class="text-xs font-bold text-ink-gray-9">{{ selectedItemToSend.item_name }}</h4>
                  <p class="mt-0.5 text-xs font-extrabold text-emerald-800">
                    {{ formatCurrency(selectedItemToSend.price, selectedItemToSend.currency) }}
                  </p>
                  <p class="mt-0.5 text-[10px] text-ink-gray-5 line-clamp-1">{{ selectedItemToSend.description }}</p>
                </div>
              </div>

              <div class="mt-2.5 border-t border-outline-gray-1 pt-2">
                <div
                  class="flex w-full items-center justify-center gap-1.5 rounded-md bg-surface-gray-2/80 py-1.5 text-xs font-semibold text-[#075E54]"
                >
                  <span class="lucide-eye size-3.5" />
                  <span>View Product</span>
                </div>
              </div>

              <p v-if="customFooterText" class="mt-1.5 text-right text-[10px] text-ink-gray-4">
                {{ customFooterText }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <template #actions>
        <div class="flex items-center justify-between w-full">
          <Button
            variant="subtle"
            label="Cancel"
            @click="showSendModal = false"
          />
          <Button
            variant="solid"
            class="bg-[#075E54] text-white hover:bg-[#128C7E]"
            :loading="isSendingProduct"
            :disabled="!recipientProfile"
            icon-left="lucide-send"
            label="Send Message"
            @click="handleSendProduct"
          />
        </div>
      </template>
    </Dialog>
  </DeskPage>
</template>
