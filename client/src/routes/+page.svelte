<script lang="ts">
	import FileUpload from "./FileUpload.svelte";
	import JSONEditorBar from "./JSONEditorBar.svelte";
    //import {LoericPlayingState, type LoericState} from "$lib/types";
	import { onMount, onDestroy } from "svelte";
	import {type LoericState} from "$lib/types";
	import Musician from "./Musician.svelte";

	let loeric_state: LoericState
	let controls = {}


	let heartbeat: ReturnType<typeof setInterval>;


	onMount(() => {
		refresh();
		heartbeat = setInterval(() => {
			fetch("/api/heartbeat", { method: "POST" });
		}, 2250);
	});

	onDestroy(() => {
		clearInterval(heartbeat);
	});


	let poller = 0
	async function refresh() {
		await apiGet('state')
		console.log(loeric_state.playing)
		if (poller) clearTimeout(poller);
		if (loeric_state.playing) poller = setTimeout(refresh, 1000);
	}


	async function trackChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("track", {track: select.value})
		await apiGet("state")
	}

	async function apiPut(call: string, payload: any) {
		const response = await fetch("/api/" + call, {
			method: 'PUT',
			headers: {"Content-Type": "application/x-www-form-urlencoded"},
			body: new URLSearchParams(payload),
		})
		loeric_state = await response.json()
	}

	async function apiGet(call: string) {
		try {
			const response = await fetch('/api/' + call);

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			loeric_state = await response.json();


		} catch (err) {
			console.error("API error:", err);
		}
	}

	async function apiUpload(call: string, form: FormData) {
		const response = await fetch("/api/" + call, {
			method: 'POST',
			body: form
		})
		loeric_state = await response.json()
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
<svelte:head><title>LOERIC</title></svelte:head>

<div class="container m-auto my-8">
	{#if loeric_state && loeric_state.options.trackList}
		<div class="flex justify-between items-center bg-gray-950 py-3 px-6 shadow-lg rounded-xl">
			<el-select onchange={trackChange} class="w-1/2 mt-2 block">
				<button type="button" class="grid w-full cursor-default grid-cols-1 rounded-md bg-transparent py-1.5 pr-2 pl-3 text-left text-white sm:text-sm/6">
					<el-selectedcontent class="col-start-1 row-start-1">

						<div class="flex items-end justify-between space-x-3 pr-6">
							<div class="text-2xl">{loeric_state.track.name.split(".")[0]}</div>
							<div class="flex space-x-3 items-center">
								{#if loeric_state.options.customized_tracks.includes(loeric_state.track.name)}
									<svg title="This track has a custom configuration." aria-hidden="true" clip-rule="evenodd" fill-rule="evenodd" xmlns="http://www.w3.org/2000/svg" class="text-gray-500" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
								{/if}
								<div title="This is a {loeric_state.track.name.split(".")[1].toUpperCase()} file." class="opacity-70 text-xl font-mono {loeric_state.track.name.split(".")[1].toUpperCase() == 'SET' ? 'text-amber-300' : ''} {loeric_state.track.name.split(".")[1].toUpperCase() == 'ABC' ? 'text-cyan-200' : ''} {loeric_state.track.name.split(".")[1].toUpperCase() == 'MID' ? 'text-pink-300' : ''}">{loeric_state.track.name.split(".")[1].toUpperCase()}</div>
							</div>
						</div>

					</el-selectedcontent>
					<svg viewBox="0 0 16 16" fill="currentColor" loeric_state-slot="icon" aria-hidden="true" class="col-start-1 row-start-1 size-5 self-center justify-self-end text-gray-500 sm:size-4">
						<path d="M5.22 10.22a.75.75 0 0 1 1.06 0L8 11.94l1.72-1.72a.75.75 0 1 1 1.06 1.06l-2.25 2.25a.75.75 0 0 1-1.06 0l-2.25-2.25a.75.75 0 0 1 0-1.06ZM10.78 5.78a.75.75 0 0 1-1.06 0L8 4.06 6.28 5.78a.75.75 0 0 1-1.06-1.06l2.25-2.25a.75.75 0 0 1 1.06 0l2.25 2.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" fill-rule="evenodd" />
					</svg>
				</button>

				<el-options anchor="bottom start" popover class="max-h-110 w-(--button-width) overflow-auto rounded-md bg-gray-950 py-1 text-white shadow-lg [--anchor-gap:--spacing(1)] loeric_state-leave:transition loeric_state-leave:transition-discrete loeric_state-leave:duration-100 loeric_state-leave:ease-in loeric_state-closed:loeric_state-leave:opacity-0 sm:text-sm">

					{#each loeric_state.options.trackList as file}
						<el-option value={file} class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">

							<div class="flex items-center justify-between gap-3 pr-6">
								<div class="text-2xl {loeric_state.track.name == file ? "text-green-200" : ''}">{file.split(".")[0]}</div>
								<div class="flex gap-3 items-center">
								{#if loeric_state.options.customized_tracks.includes(file)}
									<svg title="This track has a custom configuration." aria-hidden="true" clip-rule="evenodd" fill-rule="evenodd" xmlns="http://www.w3.org/2000/svg" class="text-gray-500" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
								{/if}
								<div title="This is a {file.split(".")[1].toUpperCase()} file." class="opacity-70 text-xl font-mono group-focus/option:text-white {file.split(".")[1].toUpperCase() == 'SET' ? 'text-amber-300' : ''} {file.split(".")[1].toUpperCase() == 'ABC' ? 'text-cyan-200' : ''} {file.split(".")[1].toUpperCase() == 'MID' ? 'text-pink-300' : ''}">{file.split(".")[1].toUpperCase()}</div>
							</div>
							</div>

							<span class="text-gren-300 absolute inset-y-0 right-0 flex items-center pr-4 group-not-aria-selected/option:hidden group-focus/option:text-white in-[el-selectedcontent]:hidden">
								<svg viewBox="0 0 20 20" fill="currentColor" loeric_state-slot="icon" aria-hidden="true" class="size-5">
									<path d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z" clip-rule="evenodd" fill-rule="evenodd" />
								</svg>
							</span>

						</el-option>
					{/each}
				</el-options>
			</el-select>
			<div><span class="opacity-70 font-light">Key:</span> {loeric_state.track.key}</div>
			<div><span class="opacity-70 font-light">Meter:</span> {loeric_state.track.time}</div>
			<div>
				<span class="opacity-70 font-light">Tempo (QPM):</span>
				<input class="text-center" type="number" onchange={tempoChange} value={loeric_state.track.tempo} min="60" max="480"/>
			</div>
			<div>
				<span class="opacity-70 font-light">Repeats:</span>
			{#if loeric_state.track.type != 'set'}
				<input class="text-center" type="number" onchange={repeatChange} value={loeric_state.track.repeats} min="1" max="100"/>
				{:else}
				<span class="text-center">{loeric_state.track.repeats}</span>

			{/if}
			</div>
			<FileUpload accepted="mid, midi, abc, audio/rtp-midi" onUpload={(file) => apiUpload('track', file)}/>
			<div>
				{#if !loeric_state.playing}
					<button class="material-symbols-outlined !text-5xl" onclick={() => {apiGet('play'); refresh(); }}> play_arrow </button>
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
		<JSONEditorBar bind:json={loeric_state.track.config} onUpload={(form) => apiUpload('track/config', form)}></JSONEditorBar>
		-->
		<div class="grid grid-cols-1 gap-4 mt-8 justify-center">
			{#each loeric_state.musicians as musician}
				<Musician musician={musician} options={loeric_state.options} apiPut={apiPut} apiUpload={apiUpload}/>
			{/each}
			<!--<div class="self-center justify-self-center">
				<button class="material-symbols-outlined" onclick={() => apiGet('add_musician')}>add</button>
			</div>
			-->
			<div class="p-3 rounded-2xl bg-gray-800 flex flex-col gap-2">
				<label class="flex flex-col">
					<span class="text-m pb-2 opacity-60">Audio Output</span>
					<select onchange={audioOutputChange}>
						{#each Object.keys(loeric_state.options.audio_outputs) as output}
							<option value={"audioOut:" + loeric_state.options.audio_outputs[output]}
								selected={loeric_state.options.selected_audio_out ===  loeric_state.options.audio_outputs[output]}>{output}</option>
						{/each}
					</select>
				</label>
			</div>
		</div>
	{/if}
</div>
