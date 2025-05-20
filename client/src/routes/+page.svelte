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
		'inputs': string[],
		'musicians': {
			id: string,
			name: string,
			midiIn: string,
			midiOut: string
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
		if (data.state === 'PLAYING') {
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

	async function inputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		const response = await fetch(base + "/api/input", {
			method: 'PUT',
			headers: {"Content-Type": "application/x-www-form-urlencoded"},
			body: new URLSearchParams({id: select.name, input: select.value}),
		})
		data = await response.json()
	}

	async function outputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		const response = await fetch(base + "/api/output", {
			method: 'PUT',
			headers: {"Content-Type": "application/x-www-form-urlencoded"},
			body: new URLSearchParams({id: select.name, output: select.value}),
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

	async function change() {
		fetch(base+ '/api/sdfsd')
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
		writing-mode: vertical-lr;
	}

	datalist {
		writing-mode: vertical-lr;
		width: 10px;
		height: 400px;
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
					<div><span class="opacity-70 font-light">Tempo:</span> {data.tempo}<span
							class="opacity-70 font-light">bpm</span></div>
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
				<div class="p-3 rounded-2xl bg-gray-800 flex flex-col gap-2">
					<div class="flex px-1">
						<div class="flex-1">{musician.name}</div>
						<div class="opacity-70 font-light">Musician</div>
					</div>
					<select name={musician.id} onchange={inputChange}>
						<option value="no_in" selected={musician.midiIn === undefined}>No Midi Input</option>
						{#each data.inputs as input}
							<option value={input} selected={musician.midiIn === input}>{input}</option>
						{/each}
					</select>
					<select name={musician.id} onchange={outputChange}>
						<option value="create_out" selected={musician.midiOut === undefined}>Create Midi Output</option>
						{#each data.outputs as output}
							<option value={output} selected={musician.midiOut === output}>{output}</option>
						{/each}
					</select>
					<div class="flex py-2">
						<input type="range" max="50" min="0" value="25" list="values"/>
						<datalist id="values">
							<option value="0" label="0"></option>
							<option value="25" label="25"></option>
							<option value="50" label="50"></option>
							<option value="75" label="75"></option>
							<option value="100" label="100"></option>
						</datalist>
						<input type="range" max="50" min="0" value="25"/>
						<input type="range" max="50" min="0" value="25"/>
					</div>
				</div>
			{/each}
			<div class="self-center justify-self-center">
				<button class="material-symbols-outlined" onclick={() => apiCall('add_musician')}>add</button>
			</div>
		</div>
	{/if}
</div>