<script lang="ts">
	export let trackname;
	export let extension;
	export let customized;
	export let is_selected;
</script>

<div class="flex items-end justify-between space-x-3 pr-6">
	<div class="text-2xl {is_selected ? "text-green-200" : ''}">{trackname}</div>
	<div class="flex space-x-3 items-center">
	{#if customized}
		<svg title="This track has a custom configuration."
			aria-hidden="true"
			clip-rule="evenodd"
			fill-rule="evenodd"
			xmlns="http://www.w3.org/2000/svg"
			class="text-gray-500"
			width="24"
			height="24"
			viewBox="0 0 24 24"
			fill="currentColor"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round">
			<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path>
			<circle cx="12" cy="7" r="4"></circle>
		</svg>
	{/if}
		<div title="This is a {extension.toUpperCase()} file."
			class="opacity-70 text-xl font-mono group-focus/option:text-white {extension.toUpperCase() == 'SET' ? 'text-amber-300' : ''} {extension.toUpperCase() == 'ABC' ? 'text-cyan-200' : ''} {extension.toUpperCase() == 'MID' ? 'text-pink-300' : ''}">
			{extension.toUpperCase()}
		</div>
	</div>
</div>
