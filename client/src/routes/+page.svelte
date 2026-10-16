<script lang="ts">
	import FileUpload from "./FileUpload.svelte";
	import JSONEditorBar from "./JSONEditorBar.svelte";
	import Tracklist from "./Tracklist.svelte";
    //import {LoericPlayingState, type LoericState} from "$lib/types";
	import { onMount, onDestroy } from "svelte";
	import {type LoericState} from "$lib/types";
	import Musician from "./Musician.svelte";

	let loeric_state: LoericState
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
			<Tracklist current_track={loeric_state.track} track_list={loeric_state.options.trackList} customized_tracks={loeric_state.options.customized_tracks} onSelected={trackChange} />

			<div>
				<span class="opacity-70 font-light">Key:</span>
			{#if loeric_state.track.type != 'set'}
				<span>{loeric_state.track.key}</span>
				{:else}
				...
			{/if}
			</div>
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
		<div class="flex w-full">
		<div class="flex-col w-1/2">
			<JSONEditorBar bind:json={loeric_state.track.custom_config} text="Custom configuration snippet" onUpload={(form) => apiUpload('track/config', form)}></JSONEditorBar>
		</div>
		<div class="flex-col w-1/2">
			<JSONEditorBar bind:json={loeric_state.track.full_config} text="Full configuration" onUpload={(form) => apiUpload('track/config', form)}></JSONEditorBar>
		</div>
		</div>
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
