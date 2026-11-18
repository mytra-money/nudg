<!-- eslint-disable vue/no-v-html -->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { Button, Dropdown, FileUploader, Tooltip } from "frappe-ui";
import MediaPreviewDialog from "../common/MediaPreviewDialog.vue";
import { formatWhatsAppMessage } from "../../utils/formatMessage";
import { contentTypeFromMime } from "../../utils/media";
import type {
	MediaFile,
	MessageInputProps,
	MessagesController,
	SendMessagePayload,
	WhatsAppContentType,
} from "./types";

/** The controller half arrives whole from `v-bind="messages"`; the rest is chrome. */
const props = withDefaults(defineProps<MessagesController & MessageInputProps>(), {
	placeholder: "Type your message here...",
	senderName: "Contact",
	youLabel: "You",
	uploadDocumentLabel: "Upload Document",
	uploadImageLabel: "Upload Image",
	uploadVideoLabel: "Upload Video",
	captionPlaceholder: "Add a caption...",
	sendLabel: "Send",
	replyingToLabel: "Replying to",
	dismissReplyLabel: "Dismiss reply",
	windowClosedLabel:
		"The 24-hour customer service window has closed. Send a template to reopen it.",
	windowUnopenedLabel: "Send a template to start the conversation.",
});

const emit = defineEmits<{
	send: [payload: SendMessagePayload];
}>();

// View state only; nothing here is part of the message being composed.
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const emojiOpen = ref(false);
const quickEmojis = ["😊", "👍", "❤️", "😂", "🙏", "😍", "✅", "🔥"];
const uploaderRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
const acceptedFileTypes = ref<string>();
const showMediaPreview = ref(false);
const draggingOver = ref(false);
// Which menu item was clicked, remembered until the upload succeeds.
const pickedType = ref<WhatsAppContentType>("document");

const draft = computed({
	get: () => props.draft,
	set: (value: string) => props.setDraft(value),
});

const replyToName = computed(() =>
	props.replyTo?.direction === "Incoming" ? props.senderName : props.youLabel
);

// The window is a guess from the loaded messages, so it only informs; Meta's own refusal
// is what stops a send that is really outside it.
const windowStatus = computed(() => props.serviceWindow?.status ?? "open");
const windowNotice = computed(() => {
	switch (windowStatus.value) {
		case "closed":
			return props.windowClosedLabel;
		case "unopened":
			return props.windowUnopenedLabel;
		default:
			return null;
	}
});
const locked = computed(() => props.disabled);
const sendable = computed(() => props.canSend && !locked.value);

function focus() {
	nextTick(() => textareaRef.value?.focus());
}

function growField() {
	const el = textareaRef.value;
	if (!el) return;
	el.style.height = "auto";
	el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

function insertEmoji(emoji: string) {
	props.setDraft(`${props.draft || ""}${emoji}`);
	emojiOpen.value = false;
	focus();
}

/**
 * The payload is built only to be reported: reading it before the send lets the emit
 * describe what went out, after the controller has cleared it.
 */
async function submit(overrides?: Pick<SendMessagePayload, "message">) {
	if (!sendable.value) return;
	const payload = props.buildPayload(overrides);
	const name = await props.send(overrides);
	if (name && payload) emit("send", payload);
}

// Shift+enter is left to the textarea, so it breaks the line. An enter that commits an IME
// composition is neither a send nor a line break.
function sendOnEnter(event: KeyboardEvent) {
	if (event.isComposing) return;
	event.preventDefault();
	submit();
}

// Preview first rather than sending immediately, so the user can add a caption.
function onUpload(file: MediaFile) {
	props.attach(file, pickedType.value);
	showMediaPreview.value = true;
}

// The caption overrides the body instead of being written into the draft, so anything
// already typed stays in the box as the separate unsent message it is.
function onMediaSend(caption: string) {
	submit({ message: caption });
}

/**
 * The accept filter is FileUploader's `fileTypes` prop, not an argument to
 * `openFileSelector()`, so it has to reach the hidden input before it is clicked.
 */
function pickFile(
	type: WhatsAppContentType,
	accept: string | undefined,
	openFileSelector: () => void
) {
	pickedType.value = type;
	acceptedFileTypes.value = accept;
	nextTick(openFileSelector);
}

function uploadOptions(openFileSelector: () => void) {
	return [
		{
			label: props.uploadDocumentLabel,
			icon: "lucide-file",
			onClick: () => pickFile("document", undefined, openFileSelector),
		},
		{
			label: props.uploadImageLabel,
			icon: "lucide-image",
			onClick: () => pickFile("image", "image/*", openFileSelector),
		},
		{
			label: props.uploadVideoLabel,
			icon: "lucide-video",
			onClick: () => pickFile("video", "video/*", openFileSelector),
		},
	];
}

/**
 * FileUploader has no method for uploading a `File` we already hold, so a dropped or
 * pasted one is handed to the input it exposes — the same path a file-picker choice takes.
 */
function upload(file: File) {
	const input = uploaderRef.value?.inputRef;
	if (!input) return;
	const kind = contentTypeFromMime(file.type);
	pickedType.value = kind === "text" ? "document" : kind;
	acceptedFileTypes.value = undefined;

	const transfer = new DataTransfer();
	transfer.items.add(file);
	input.files = transfer.files;
	input.dispatchEvent(new Event("change"));
}

function onDrop(event: DragEvent) {
	draggingOver.value = false;
	const file = event.dataTransfer?.files?.[0];
	if (file && !locked.value) upload(file);
}

// Only when the clipboard actually carries a file — pasting text must stay a paste.
function onPaste(event: ClipboardEvent) {
	const file = event.clipboardData?.files?.[0];
	if (!file || locked.value) return;
	event.preventDefault();
	upload(file);
}

watch(
	() => props.replyTo,
	(value) => value && focus()
);

watch(draft, () => nextTick(growField));

// Dismissing the preview abandons the upload; leaving it staged would attach it to whatever
// is typed next. A send has already cleared it by the time this runs.
watch(showMediaPreview, (open) => {
	if (!open && props.pendingMedia) props.clearAttachment();
});

defineExpose({ focus });
</script>

<template>
	<!-- The dialog is a sibling of the composer, so a host's `class` needs a root above both. -->
	<div class="flex flex-col gap-2">
		<div
			v-if="windowNotice"
			role="status"
			class="flex items-center gap-2 rounded-lg bg-white/80 px-3 py-2 text-xs text-[#667781]"
		>
			<span class="lucide-info size-4 shrink-0 text-amber-600" aria-hidden="true" />
			{{ windowNotice }}
		</div>

		<div
			v-if="replyTo"
			class="flex items-center gap-2 rounded-lg bg-white px-2.5 py-2 shadow-sm"
		>
			<div class="min-w-0 flex-1 border-l-2 border-[#00A884] pl-2">
				<div class="text-xs font-medium text-[#00A884]">
					{{ replyingToLabel }} {{ replyToName }}
				</div>
				<div
					class="line-clamp-2 text-sm text-[#111B21]"
					v-html="formatWhatsAppMessage(replyTo.message)"
				/>
			</div>
			<Button variant="ghost" :aria-label="dismissReplyLabel" @click="clearReply()">
				<template #icon>
					<span class="lucide-x size-4 text-[#667781]" aria-hidden="true" />
				</template>
			</Button>
		</div>

		<div
			class="flex items-end gap-1.5"
			:class="draggingOver ? 'rounded-lg bg-emerald-50/80' : ''"
			@dragover.prevent="draggingOver = true"
			@dragleave="draggingOver = false"
			@drop.prevent="onDrop"
			@paste="onPaste"
		>
			<div class="relative shrink-0">
				<button
					type="button"
					class="grid size-10 place-items-center rounded-full text-[#54656F] hover:bg-black/5"
					aria-label="Insert emoji"
					:disabled="locked"
					@click="emojiOpen = !emojiOpen"
				>
					<span class="text-xl leading-none" aria-hidden="true">😊</span>
				</button>
				<div
					v-if="emojiOpen"
					class="absolute bottom-12 left-0 z-20 flex gap-0.5 rounded-full border border-[#E9EDEF] bg-white px-1.5 py-1 shadow-md"
				>
					<button
						v-for="emoji in quickEmojis"
						:key="emoji"
						type="button"
						class="grid size-8 place-items-center rounded-full text-lg hover:bg-[#F0F2F5]"
						:aria-label="`Insert ${emoji}`"
						@click="insertEmoji(emoji)"
					>
						{{ emoji }}
					</button>
				</div>
			</div>

			<FileUploader
				ref="uploaderRef"
				:file-types="acceptedFileTypes"
				@success="onUpload"
			>
				<template #default="{ openFileSelector }">
					<Dropdown :options="uploadOptions(openFileSelector)">
						<button
							type="button"
							class="grid size-10 shrink-0 place-items-center rounded-full text-[#54656F] hover:bg-black/5 disabled:opacity-40"
							:disabled="locked"
							aria-label="Attach a file"
						>
							<span class="lucide-paperclip size-5" aria-hidden="true" />
						</button>
					</Dropdown>
				</template>
			</FileUploader>

			<div class="flex shrink-0 items-center">
				<slot name="leading-actions" />
			</div>

			<textarea
				ref="textareaRef"
				v-model="draft"
				rows="1"
				class="max-h-40 min-h-10 min-w-0 flex-1 resize-none rounded-lg border-0 bg-white px-4 py-2.5 text-sm leading-5 text-[#111B21] shadow-sm outline-none placeholder:text-[#667781] focus:ring-1 focus:ring-emerald-500 disabled:opacity-60"
				:placeholder="placeholder"
				:disabled="locked"
				@input="growField"
				@keydown.enter.exact="sendOnEnter"
			/>

			<Tooltip>
				<template #content>
					<span class="flex items-center gap-1">
						{{ sendLabel }}
						<kbd class="rounded bg-white/15 px-1 text-xs">↵</kbd>
					</span>
				</template>
				<button
					type="button"
					class="grid size-10 shrink-0 place-items-center rounded-full bg-[#00A884] text-white hover:bg-[#008f6f] disabled:opacity-40"
					:disabled="!sendable"
					:aria-label="sendLabel"
					@click="submit()"
				>
					<span
						v-if="sending"
						class="lucide-loader-2 size-4 animate-spin"
						aria-hidden="true"
					/>
					<span v-else class="lucide-send size-4" aria-hidden="true" />
				</button>
			</Tooltip>
		</div>

		<MediaPreviewDialog
			v-model:open="showMediaPreview"
			:file="pendingMedia"
			:type="pendingType"
			:loading="sending"
			:caption-placeholder="captionPlaceholder"
			@send="onMediaSend"
		/>
	</div>
</template>
