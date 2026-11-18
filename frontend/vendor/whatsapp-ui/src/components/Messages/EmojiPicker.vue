<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";

interface EmojiMartEmoji {
	id: string;
	name: string;
	keywords?: string[];
	emoticons?: string[];
	skins: { native: string }[];
}

interface EmojiMartData {
	categories: { id: string; emojis: string[] }[];
	emojis: Record<string, EmojiMartEmoji>;
}

interface EmojiSection {
	id: string;
	label: string;
	icon: string;
	emojis: EmojiMartEmoji[];
}

const emit = defineEmits<{
	select: [emoji: string];
}>();

const SKIN_KEY = "nudg-emoji-skin";
const RECENT_KEY = "nudg-emoji-recent";
const TONES = ["👋", "👋🏻", "👋🏼", "👋🏽", "👋🏾", "👋🏿"];

const CATEGORIES = [
	{ id: "recent", label: "Recently used", icon: "🕒" },
	{ id: "people", label: "Smileys & people", icon: "😊" },
	{ id: "nature", label: "Animals & nature", icon: "🐶" },
	{ id: "foods", label: "Food & drink", icon: "🍔" },
	{ id: "activity", label: "Activity", icon: "⚽" },
	{ id: "places", label: "Travel & places", icon: "🚗" },
	{ id: "objects", label: "Objects", icon: "💡" },
	{ id: "symbols", label: "Symbols", icon: "🔣" },
	{ id: "flags", label: "Flags", icon: "🏳️" },
] as const;

type CategoryId = (typeof CATEGORIES)[number]["id"];

const data = ref<EmojiMartData | null>(null);
const failed = ref(false);
const query = ref("");
const skin = ref(0);
const tonesOpen = ref(false);
const recentIds = ref<string[]>([]);
const active = ref<CategoryId>("people");
const scroller = ref<HTMLElement | null>(null);
const searchRef = ref<HTMLInputElement | null>(null);

onMounted(async () => {
	skin.value = readSkin();
	recentIds.value = readRecent();
	try {
		const mod = (await import("@emoji-mart/data")) as { default: EmojiMartData };
		data.value = mod.default;
	} catch {
		failed.value = true;
	}
	nextTick(() => searchRef.value?.focus());
});

function readSkin() {
	try {
		const stored = Number(localStorage.getItem(SKIN_KEY));
		return stored >= 0 && stored < TONES.length ? stored : 0;
	} catch {
		return 0;
	}
}

function readRecent() {
	try {
		const parsed = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
		return Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : [];
	} catch {
		return [];
	}
}

function glyph(emoji: EmojiMartEmoji) {
	if (emoji.skins.length < 2) return emoji.skins[0]?.native || "";
	return (emoji.skins[skin.value] ?? emoji.skins[0])?.native || "";
}

function lookup(id: string) {
	return data.value?.emojis[id];
}

const catalog = computed(() => {
	if (!data.value) return [];
	return CATEGORIES.filter((category) => category.id !== "recent")
		.map((category) => {
			const source = data.value?.categories.find((entry) => entry.id === category.id);
			const emojis = (source?.emojis || [])
				.map((id) => lookup(id))
				.filter((emoji): emoji is EmojiMartEmoji => Boolean(emoji));
			return { ...category, emojis };
		})
		.filter((category) => category.emojis.length);
});

const recent = computed(() =>
	recentIds.value
		.map((id) => lookup(id))
		.filter((emoji): emoji is EmojiMartEmoji => Boolean(emoji))
);

const sections = computed((): EmojiSection[] => {
	const rows: EmojiSection[] = catalog.value.map((category) => ({ ...category }));
	if (recent.value.length) {
		rows.unshift({
			id: "recent",
			label: "Recently used",
			icon: "🕒",
			emojis: recent.value,
		});
	}
	return rows;
});

const results = computed(() => {
	const needle = query.value.trim().toLowerCase();
	if (!needle || !data.value) return [];
	const found: EmojiMartEmoji[] = [];
	for (const category of catalog.value) {
		for (const emoji of category.emojis) {
			const haystack = [emoji.name, ...(emoji.keywords || []), ...(emoji.emoticons || [])]
				.join(" ")
				.toLowerCase();
			if (haystack.includes(needle)) found.push(emoji);
		}
	}
	return found;
});

const tabs = computed(() =>
	CATEGORIES.filter((category) => category.id !== "recent" || recent.value.length)
);

function choose(emoji: EmojiMartEmoji) {
	const native = glyph(emoji);
	if (!native) return;
	recentIds.value = [emoji.id, ...recentIds.value.filter((id) => id !== emoji.id)].slice(0, 40);
	localStorage.setItem(RECENT_KEY, JSON.stringify(recentIds.value));
	emit("select", native);
}

function setSkin(index: number) {
	skin.value = index;
	tonesOpen.value = false;
	localStorage.setItem(SKIN_KEY, String(index));
}

function showCategory(id: CategoryId) {
	active.value = id;
	query.value = "";
	nextTick(() => {
		scroller.value
			?.querySelector(`[data-category="${id}"]`)
			?.scrollIntoView({ block: "start" });
	});
}

function onScroll() {
	const root = scroller.value;
	if (!root || query.value.trim()) return;
	const top = root.getBoundingClientRect().top;
	let current: CategoryId = active.value;
	for (const section of root.querySelectorAll<HTMLElement>("[data-category]")) {
		if (section.getBoundingClientRect().top - top <= 12) {
			current = section.dataset.category as CategoryId;
		}
	}
	active.value = current;
}
</script>

<template>
	<div
		class="absolute bottom-12 left-0 z-30 flex w-[22rem] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-xl border border-[#E9EDEF] bg-white shadow-lg"
		role="dialog"
		aria-label="Emoji"
	>
		<div class="flex items-center gap-1.5 border-b border-[#E9EDEF] px-2 py-2">
			<input
				ref="searchRef"
				v-model="query"
				type="search"
				placeholder="Search emoji"
				aria-label="Search emoji"
				class="h-8 min-w-0 flex-1 rounded-lg bg-[#F0F2F5] px-3 text-sm text-[#111B21] outline-none placeholder:text-[#667781]"
			/>
			<div class="relative shrink-0">
				<button
					type="button"
					class="grid size-8 place-items-center rounded-full text-lg hover:bg-[#F0F2F5]"
					aria-label="Skin tone"
					:aria-expanded="tonesOpen"
					@click="tonesOpen = !tonesOpen"
				>
					{{ TONES[skin] }}
				</button>
				<div
					v-if="tonesOpen"
					class="absolute right-0 top-9 z-10 flex gap-0.5 rounded-full border border-[#E9EDEF] bg-white p-1 shadow-md"
				>
					<button
						v-for="(tone, index) in TONES"
						:key="tone"
						type="button"
						class="grid size-8 place-items-center rounded-full text-lg hover:bg-[#F0F2F5]"
						:class="index === skin ? 'bg-[#F0F2F5]' : ''"
						:aria-label="`Skin tone ${index + 1}`"
						@click="setSkin(index)"
					>
						{{ tone }}
					</button>
				</div>
			</div>
		</div>

		<div
			ref="scroller"
			class="min-h-[16.5rem] overflow-y-auto px-1.5 py-1"
			@scroll="onScroll"
		>
			<p v-if="failed" class="px-2 py-6 text-center text-sm text-[#667781]">
				Emojis could not be loaded.
			</p>
			<p v-else-if="!data" class="px-2 py-6 text-center text-sm text-[#667781]">
				Loading emojis…
			</p>
			<p
				v-else-if="query.trim() && !results.length"
				class="px-2 py-6 text-center text-sm text-[#667781]"
			>
				No emojis found.
			</p>
			<div v-else-if="query.trim()" class="grid grid-cols-8">
				<button
					v-for="emoji in results"
					:key="emoji.id"
					type="button"
					class="grid h-9 place-items-center rounded-md text-[1.35rem] leading-none hover:bg-[#F0F2F5]"
					:title="emoji.name"
					:aria-label="emoji.name"
					@click="choose(emoji)"
				>
					{{ glyph(emoji) }}
				</button>
			</div>
			<section
				v-for="section in query.trim() ? [] : sections"
				:key="section.id"
				:data-category="section.id"
				class="[content-visibility:auto]"
			>
				<h3
					class="sticky top-0 z-[1] bg-white px-1.5 py-1 text-[11px] font-semibold text-[#667781]"
				>
					{{ section.label }}
				</h3>
				<div class="grid grid-cols-8">
					<button
						v-for="emoji in section.emojis"
						:key="`${section.id}-${emoji.id}`"
						type="button"
						class="grid h-9 place-items-center rounded-md text-[1.35rem] leading-none hover:bg-[#F0F2F5]"
						:title="emoji.name"
						:aria-label="emoji.name"
						@click="choose(emoji)"
					>
						{{ glyph(emoji) }}
					</button>
				</div>
			</section>
		</div>

		<div class="flex border-t border-[#E9EDEF] px-1 py-1">
			<button
				v-for="category in tabs"
				:key="category.id"
				type="button"
				class="grid h-8 min-w-0 flex-1 place-items-center rounded-md text-base hover:bg-[#F0F2F5]"
				:class="!query.trim() && active === category.id ? 'bg-[#F0F2F5]' : ''"
				:aria-label="category.label"
				@click="showCategory(category.id)"
			>
				{{ category.icon }}
			</button>
		</div>
	</div>
</template>
