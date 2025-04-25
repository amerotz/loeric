<script lang="ts">
	import {onMount} from "svelte"

	let data: any
	let base = "http://localhost:8080"

	onMount(update)

	async function update() {
		const response = await fetch(base + '/api/state')
		data = await response.json()
	}

	async function play() {
		const response = await fetch(base + "/api/play")
		data = await response.json()
	}

	async function stop() {
		const response = await fetch(base + "/api/stop")
		data = await response.json()
	}

	async function trackChange(event: Event) {
		const response = await fetch(base + "/api/track", {
			method: 'PUT',
			headers: {"Content-Type": "application/x-www-form-urlencoded"},
			body: new URLSearchParams({track: (event.target as HTMLSelectElement).value}),
		})
		data = await response.json()
	}
</script>

<style>
	button {
		@apply transition-all cursor-pointer hover:opacity-75;
	}
</style>

<div class="container m-auto">
	{#if data && data.trackList}
		<select class="text-2xl" onchange={trackChange}>
			{#each data.trackList as file}
				<option value={file} selected={file === data.track}>{file.replace(/\.mid$/i, '')}</option>
			{/each}
		</select>
		<div>
			<div>Key: {data.key}</div>
			<div>Time: {data.time}</div>
		</div>
		<form action="/api/track" class="hidden">
			<input type="file" accept="audio/rtp-midi"/>
		</form>
		<button class="material-symbols-outlined">upload</button>

		<button class="material-symbols-outlined" onclick={play}>play_arrow</button>

		<button class="material-symbols-outlined" onclick={stop}>stop</button>

		<div>
			{#each data.musicians as musician}
				<select>
					<option value="create_out" selected={musician.out === undefined}>Create Out</option>
					{#each data.outputs as output}
						<option value={output} selected={musician.out === output}>{output}</option>
					{/each}
				</select>
			{/each}
		</div>
	{/if}
</div>