<script lang="ts">
	export let name;
	export let is_synth;
</script>

<div class="flex items-start space-x-3 pr-6">
	{#if is_synth}
		<svg xmlns="http://www.w3.org/2000/svg"
			width="24"
			height="24"
			viewBox="0 0 24 24"
			fill="none"
			stroke="#ffffff"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round">
			<rect width="16" height="20" x="4" y="2" rx="2"></rect>
			<path d="M12 6h.01"></path>
			<circle cx="12" cy="14" r="4"></circle>
			<path d="M12 14h.01"></path>
		</svg>
		<div class="text-m">LOERIC Built-in Synth</div>
	{:else}
		<svg xmlns="http://www.w3.org/2000/svg"
			width="24"
			height="24"
			viewBox="0 0 24 24"
			fill="none"
			stroke="#ffffff"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round">
			<rect width="20" height="16" x="2" y="4" rx="2"></rect>
			<path d="M6 8h4"></path>
			<path d="M14 8h.01"></path>
			<path d="M18 8h.01"></path>
			<path d="M2 12h20"></path>
			<path d="M6 12v4"></path>
			<path d="M10 12v4"></path>
			<path d="M14 12v4"></path>
			<path d="M18 12v4"></path>
		</svg>
		<div class="text-m">{name}</div>
	{/if}
</div>
