<script lang="ts">
	import FileUpload from "./FileUpload.svelte";
	import JSONEditorBar from "./JSONEditorBar.svelte";
	import {LoericPlayingState, type LoericState} from "$lib/types";
	import {onMount} from "svelte"
	import Musician from "./Musician.svelte";

	let data: LoericState

	let base = "http://localhost:8080"

	export let audioOutput : string

	onMount(refresh)
	let poller = 0

	async function refresh() {
		await apiGet('state')
	}

	async function trackChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("track", {track: select.value})
	}

	async function apiPut(call: string, data: any) {
		const response = await fetch(base + "/api/" + call, {
			method: 'PUT',
			headers: {"Content-Type": "application/x-www-form-urlencoded"},
			body: new URLSearchParams(data),
		})
		data = await response.json()
	}

	async function apiGet(call: string) {
		const response = await fetch(base + '/api/' + call)
		data = await response.json()
		clearTimeout(poller)
		if (data.state === LoericPlayingState.PLAYING) {
			poller = setTimeout(refresh, 500)
		}
	}

	async function apiUpload(call: string, form: FormData) {
		const response = await fetch(base + "/api/" + call, {
			method: 'POST',
			body: form
		})
		data = await response.json()
	}

	async function tempoChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("tempo", {tempo: select.value})
	}

	async function audioOutputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("audio_out", {device: select.value})
	}

</script>

<svelte:head><title>Loeric</title></svelte:head>

<div class="container m-auto my-8">
	{#if data && data.options.trackList}
		<div class="flex items-center bg-gray-950 py-3 px-6 rounded-xl">
			<div class="flex-1">
				<select class="w-full text-3xl" onchange={trackChange}>
					{#each data.options.trackList as file}
						<option value={file} selected={file === data.track.name}>{file.replace(/\.mid$/i, '').replace(/\.abc$/i, '')}</option>
					{/each}
				</select>
				<div class="px-1 flex gap-2">
					<div><span class="opacity-70 font-light">Key:</span> {data.track.key}</div>
					<div><span class="opacity-70 font-light">Meter:</span> {data.track.time}</div>
					<div><span class="opacity-70 font-light">Tempo:</span> <input type="number" onchange={tempoChange} value={data.track.tempo}
					                                                              min="60" max="480"/><span
							class="opacity-70 font-light">QPM</span></div>
					<FileUpload accepted="mid, midi, audio/rtp-midi" onUpload={(file) => apiUpload('track', file)}/>
				</div>
			</div>
			<div>
				{#if data.state !== LoericPlayingState.PLAYING}
					<button class="material-symbols-outlined !text-5xl" onclick={() => apiGet('play')}>
						play_arrow
					</button>
				{:else}
					<button class="material-symbols-outlined !text-5xl" onclick={() => apiGet('pause')}>
						pause
					</button>
					<button class="material-symbols-outlined !text-5xl" onclick={() => apiGet('stop')}>
						stop
					</button>
				{/if}
			</div>
		</div>
		<!--
		<JSONEditorBar bind:json={data.track.config} onUpload={(form) => apiUpload('track/config', form)}></JSONEditorBar>
		-->
		<div class="grid grid-cols-1 gap-4 mt-8">
			{#each data.musicians as musician}
				<div class="p-3 rounded-2xl bg-gray-800 flex flex-col gap-2">
					<Musician musician={musician} options={data.options} apiPut={apiPut} apiUpload={apiUpload}/>
				</div>
			{/each}
		<!--<div class="self-center justify-self-center">
				<button class="material-symbols-outlined" onclick={() => apiGet('add_musician')}>add</button>
			</div>
		-->
			<div class="p-3 rounded-2xl bg-gray-800 flex flex-col gap-2">
				<label class="flex flex-col">
					<span class="text-m pb-2 opacity-60">Audio Output</span>
					<select onchange={audioOutputChange}>
						{#each Object.keys(data.options.audio_outputs) as output}
							<option value={"audioOut:" + data.options.audio_outputs[output]}
									selected={audioOutput=== "audioOut:" + data.options.audio_outputs[output]}>{output}</option>
						{/each}
						{#each data.options.output as output}
							<option value={output} selected={audioOutput=== output}>{output}</option>
						{/each}
					</select>
				</label>
			</div>
		</div>
	{/if}
</div>
