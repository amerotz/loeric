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

	async function repeatChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("repeat", {repeats: select.value})
	}

	async function audioOutputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("audio_out", {device: select.value})
	}

</script>
<svelte:head><title>Loeric</title></svelte:head>

<div class="container m-auto my-8">
	{#if data && data.options.trackList}
		<div class="flex justify-between items-center bg-gray-950 py-3 px-6 rounded-xl">
			<el-select class="flex w-1/2 gap-5 items-center" onchange={trackChange}>
				<button type="button" class="flex w-full items-center gap-2"> 
					<el-selectedcontent class="flex w-full items-center justify-between cursor-default rounded-md bg-transparent text-left hover:text-primary text-white">
						<div class="text-3xl w-5/6">{data.track.name.split(".")[0]}</div>
						<div class="opacity-70 text-xl">{data.track.name.split(".")[1].toUpperCase()}</div>
					</el-selectedcontent>
						<svg viewBox="0 0 16 16" fill="currentColor" data-slot="icon" aria-hidden="true" class="size-5 justify-self-end text-gray-500 sm:size-4">
							<path d="M5.22 10.22a.75.75 0 0 1 1.06 0L8 11.94l1.72-1.72a.75.75 0 1 1 1.06 1.06l-2.25 2.25a.75.75 0 0 1-1.06 0l-2.25-2.25a.75.75 0 0 1 0-1.06ZM10.78 5.78a.75.75 0 0 1-1.06 0L8 4.06 6.28 5.78a.75.75 0 0 1-1.06-1.06l2.25-2.25a.75.75 0 0 1 1.06 0l2.25 2.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" fill-rule="evenodd" />
						</svg>
				</button>
				<el-options anchor="bottom start" class="
					w-1/2 bg-gray-950 text-white rounded-xl py-3 px-6">
					{#each data.options.trackList as file}
						<el-option class="
							relative block cursor-default py-2 pr-9 pl-3 select-none 
hover:text-primary
							flex w-full items-baselins-last justify-between group/option" value={file}>
							<div class="text-3xl w-5/6">{file.split(".")[0]}</div>
							<div class="opacity-70 text-xl">{file.split(".")[1].toUpperCase()}</div>
						</el-option>
					{/each}
				</el-options>
			</el-select>
			<div><span class="opacity-70 font-light">Key:</span> {data.track.key}</div>
			<div><span class="opacity-70 font-light">Meter:</span> {data.track.time}</div>
			<div>
				<span class="opacity-70 font-light">Tempo (QPM):</span>
				<input class="text-center" type="number" onchange={tempoChange} value={data.track.tempo} min="60" max="480"/>
			</div>
			<div>
				<span class="opacity-70 font-light">Repeats:</span>
				<input class="text-center" type="number" onchange={repeatChange} value={data.track.repeats} min="1" max="100"/>
			</div>
			<FileUpload accepted="mid, midi, audio/rtp-midi" onUpload={(file) => apiUpload('track', file)}/>
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
