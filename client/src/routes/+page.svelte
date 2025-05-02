<script lang="ts">
	import {onMount} from "svelte"

	let data: {
		'time': string,
		'key': string,
		'track': string,
		'tempo': number,
		'state': string,
		'trackList': string[],
		'outputs': string[],
		'musicians': {
			name: string,
			out: string
		}[],
	}
	let base = "http://localhost:8080"

	let fileInput: HTMLInputElement

	onMount(refresh)
	let poller = 0

	async function refresh() {
		await apiCall('state')
	}

	async function apiCall(call: string) {
		const response = await fetch(base + '/api/' + call)
		data = await response.json()
		clearTimeout(poller)
		if(data.state === 'PLAYING') {
			poller = setTimeout(refresh, 500)
		}
	}

	async function trackChange(event: Event) {
		const response = await fetch(base + "/api/track", {
			method: 'PUT',
			headers: {"Content-Type": "application/x-www-form-urlencoded"},
			body: new URLSearchParams({track: (event.target as HTMLSelectElement).value}),
		})
		data = await response.json()
	}

	async function upload() {
		const formData = new FormData()
		const file = fileInput.files?.item(0)
		if (file) {
			formData.append('upload', file)
			const response = await fetch(base + "/api/track", {
				method: 'POST',
				body: formData
			})
			data = await response.json()
		}
	}

	async function selectFile() {
		fileInput.click()
	}
</script>

<svelte:head><title>Loeric</title></svelte:head>

<div class="container m-auto my-8">
	{#if data && data.trackList}
		<div class="flex items-center bg-gray-950 py-3 px-6 rounded-xl">
			<div class="flex-1">
				<select class="w-full text-3xl" onchange={trackChange}>
					{#each data.trackList as file}
						<option value={file} selected={file === data.track}>{file.replace(/\.mid$/i, '')}</option>
					{/each}
				</select>
				<div class="px-1 flex gap-2">
					<div><span class="opacity-70 font-light">Key:</span> {data.key}</div>
					<div><span class="opacity-70 font-light">Meter:</span> {data.time}</div>
					<div><span class="opacity-70 font-light">Tempo:</span> {data.tempo}<span class="opacity-70 font-light">bpm</span></div>
					<input class="hidden" type="file" accept="mid, midi, audio/rtp-midi" name="upload" onchange={upload}
					       bind:this={fileInput}/>
					<button class="material-symbols-outlined" onclick={selectFile}>upload</button>
				</div>
			</div>
			<div>
				{#if data.state !== 'PLAYING'}
					<button class="material-symbols-outlined !text-5xl" onclick={() => apiCall('play')}>
						play_arrow
					</button>
				{:else}
					<button class="material-symbols-outlined !text-5xl" onclick={() => apiCall('pause')}>
						pause
					</button>
					<button class="material-symbols-outlined !text-5xl" onclick={() => apiCall('stop')}>
						stop
					</button>
				{/if}
			</div>
		</div>
		<div class="grid grid-cols-3 gap-4 mt-8">
			{#each data.musicians as musician}
				<div class="p-3 rounded-2xl bg-gray-900">
					<div><span class="opacity-70 font-light">Musician</span> {musician.name}</div>
					<select>
						<option value="create_out" selected={musician.out === undefined}>Create Out</option>
						{#each data.outputs as output}
							<option value={output} selected={musician.out === output}>{output}</option>
						{/each}
					</select>
				</div>
			{/each}
			<div class="self-center justify-self-center">
				<button class="material-symbols-outlined" onclick={() => apiCall('add_musician')}>add</button>
			</div>
		</div>
	{/if}
</div>