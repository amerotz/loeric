<script lang="ts">
	import {onMount} from "svelte";

	let data: any

	async function update() {
		const response = await fetch('/api/state')
		data = await response.json()
	}

	onMount(async () => {
		await update()
	})
</script>

{#if data && data.trackList}
	<select class="text-2xl">
		{#each data.trackList as file}
			<option value={file}>{file.replace(/\.mid$/i, '')}</option>
		{/each}
	</select>
	<form action="/api/track">
		<input type="file" accept="audio/rtp-midi"/>
	</form>
	<button class="material-symbols-outlined">upload</button>
{/if}
