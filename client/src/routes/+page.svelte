<script lang="ts">
	import {onMount} from "svelte"

	let data: {
		'track': {
			'name': string,
			'time': string,
			'key': string,
			'tempo': number,
		},
		'state': string,
		'options': {
			'trackList': string[],
			'outputs': string[],
			'inputs': string[],
			'instruments': string[],
			'audio': {[id: string]: number}
		}
		'musicians': {
			id: string,
			name: string,
			midiIn: string,
			midiOut: string,
			instrument: string,
			controls: {
				name: string,
				control: number,
				value: number
			}[]
		}[],
	}

	let base = "http://localhost:8080"

	let fileInput: HTMLInputElement

	onMount(refresh)
	let poller = 0

	async function refresh() {
		await apiGet('state')
	}

	async function trackChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("instrument", {track: select.value})
	}

	async function inputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("input", {id: select.name, input: select.value})
	}

	async function outputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("output", {id: select.name, output: select.value})
	}

	async function instrumentChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("instrument", {id: select.name, instrument: select.value})
	}

	async function controlChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("control", {id: select.name, control: select.getAttribute("data-control"), volume: select.value})
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
		if (data.state === 'PLAYING') {
			poller = setTimeout(refresh, 500)
		}
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

<style lang="postcss">
	input[type="range"] {
		-webkit-appearance: none;
		appearance: none;
		background: transparent;
		width: 60px;
		height: 400px;
		direction: rtl;
		writing-mode: vertical-lr;
	}

	input[type="range"]::-webkit-slider-runnable-track {
		background: #000;
		width: 0.5rem;
		border-radius: 1rem;
		border: 1px solid #444;
		border-top-color: #000;
		border-left-color: #000;
	}

	input[type=range]::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 50px;
		height: 64px;
		margin-left: -22px;
		border: 0;
		background: url("fader_knob.svg");
		background-size: contain;
		cursor: pointer;
	}
</style>

<div class="container m-auto my-8">
	{#if data && data.options.trackList}
		<div class="flex items-center bg-gray-950 py-3 px-6 rounded-xl">
			<div class="flex-1">
				<select class="w-full text-3xl" onchange={trackChange}>
					{#each data.options.trackList as file}
						<option value={file} selected={file === data.track.name}>{file.replace(/\.mid$/i, '')}</option>
					{/each}
				</select>
				<div class="px-1 flex gap-2">
					<div><span class="opacity-70 font-light">Key:</span> {data.track.key}</div>
					<div><span class="opacity-70 font-light">Meter:</span> {data.track.time}</div>
					<div><span class="opacity-70 font-light">Tempo:</span> <input type="number" value={data.track.tempo} min="60" max="480"/><span
							class="opacity-70 font-light">bpm</span></div>
					<input class="hidden" type="file" accept="mid, midi, audio/rtp-midi" name="upload" onchange={upload}
					       bind:this={fileInput}/>
					<button class="material-symbols-outlined" onclick={selectFile}>upload</button>
				</div>
			</div>
			<div>
				{#if data.state !== 'PLAYING'}
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
		<div class="grid grid-cols-3 gap-4 mt-8">
			{#each data.musicians as musician}
				<div class="p-3 rounded-2xl bg-gray-800 flex flex-col gap-2">
					<div class="flex px-1">
						<div class="flex-1 font-semibold">{musician.name}</div>
						<div class="opacity-60 font-light">Musician</div>
					</div>
					<label class="flex flex-col">
						<span class="text-xs px-1 opacity-60">Instrument</span>
						<select name={musician.id} onchange={instrumentChange}>
							{#each data.options.instruments as instrument}
								<option value={instrument}
								        selected={musician.instrument === instrument}>{instrument}</option>
							{/each}
						</select>
					</label>
					<label class="flex flex-col">
						<span class="text-xs px-1 opacity-60">Output</span>
						<select name={musician.id} onchange={outputChange}>
							<option value="synth" selected={musician.midiOut?.startsWith("Loeric Synth ")}>Loeric
								Synth
							</option>
							<option value="create_out" selected={musician.midiOut?.startsWith("Loeric Out ")}>Midi
								Output
							</option>
							{#each data.options.outputs as output}
								<option value={output} selected={musician.midiOut === output}>{output}</option>
							{/each}
						</select>
					</label>
					<label class="flex flex-col">
						<span class="text-xs px-1 opacity-60">Input</span>
						<select name={musician.id} onchange={inputChange}>
							<option value="no_in" selected={musician.midiIn === undefined}>None</option>
							{#each Object.keys(data.options.audio) as input}
								<option value={"audioIn:" + data.options.audio[input]} selected={musician.midiIn === "audioIn:" + data.options.audio[input]}>{input}</option>
							{/each}
							{#each data.options.inputs as input}
								<option value={input} selected={musician.midiIn === input}>{input}</option>
							{/each}
						</select>
					</label>
					<div class="flex py-2 self-center">
						{#each musician.controls as control}
							<label class="flex flex-col items-center gap-1">
								<span class="text-xs text-center">{control.name}</span>
								<input type="range" max="127" min="0" name={musician.id} data-control={control.control} value={control.value} onchange={controlChange}/>
							</label>
						{/each}
					</div>
				</div>
			{/each}
			<div class="self-center justify-self-center">
				<button class="material-symbols-outlined" onclick={() => apiGet('add_musician')}>add</button>
			</div>
		</div>
	{/if}
</div>