declare module "@emoji-mart/data" {
	const data: {
		categories: { id: string; emojis: string[] }[];
		emojis: Record<
			string,
			{
				id: string;
				name: string;
				keywords?: string[];
				emoticons?: string[];
				skins: { native: string }[];
			}
		>;
	};
	export default data;
}
