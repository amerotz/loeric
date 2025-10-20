<script lang="ts">
	import type {Musician, Options} from "$lib/types";
	import JSONEditorBar from "./JSONEditorBar.svelte";

	export let musician: Musician
	export let options: Options
	export let apiPut: (action: string, data: any) => Promise<void> = async (_1, _2) => {}
	export let apiUpload: (action: string, form: FormData) => Promise<void> = async (_1, _2) => {}
	export let droning = musician.droning
	export let slow_start = musician.slow_start
	export let slow_end = musician.slow_end
	export let transpose = musician.transpose

	async function inputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("input", {id: musician.id, input: select.value})
	}

	async function outputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("output", {id: musician.id, output: select.value})
	}

	async function instrumentChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("instrument", {id: musician.id, instrument: select.value})
	}

	async function droningChange(event: Event) {
		await apiPut("drones", {id: musician.id, drones: droning})
	}
	async function startChange(event: Event) {
		await apiPut("slow_start", {id: musician.id, slow_start: slow_start})
	}
	async function endChange(event: Event) {
		await apiPut("slow_end", {id: musician.id, slow_end: slow_end})
	}
	async function transposeChange(event: Event) {
		await apiPut("transpose", {id: musician.id, transpose: transpose})
	}

	async function controlChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("control", {id: musician.id, control: select.getAttribute("data-control"), value: select.value})
	}

	async function uploadConfig(form: FormData) {
		form.append('id', musician.id)
		await apiUpload('musician/config', form)
	}
</script>

<style lang="postcss">
	input[type="range"] {
		-webkit-appearance: none;
		appearance: auto;
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
		appearance: auto;
		width: 50px;
		height: 64px;
		margin-left: -22px;
		border: 0;
		background: url("../assets/fader_knob.svg");
		background-size: contain;
		cursor: pointer;
	}
</style>

<div class="flex flex-col p-5 shadow-lg rounded-2xl bg-gray-800 flex gap-2">
	<div class="flex text-lg">
		<div class="flex-1 font-semibold">{musician.name}</div> <!--<div class="opacity-60 font-light">Musician</div>-->
	</div>
	<div class="flex text-lg justify-start gap-5">
		<div class="bg-gray-700 rounded-2xl h-full">
			<!--<JSONEditorBar json={musician.config} onUpload={uploadConfig}></JSONEditorBar>-->
			<div class="flex flex-col p-5 gap-5">
				<div class="flex justify-between gap-5">
					<label class="flex flex-col">
						<span class="opacity-60 font-bold">INSTRUMENT</span>
						<select class="" onchange={instrumentChange}>
							{#each options.instruments as instrument}
								<option value={instrument} selected={musician.instrument === instrument}>{instrument}</option>
							{/each}
						</select>
					</label>
					<label class="flex flex-col gap-3">
						<label>
							<div class="flex gap-3 justify-between">
								<span class="opacity-60 font-bold">DRONES</span>
								<input class="col-span-1" type="checkbox" bind:checked={droning} onchange={droningChange}>
							</div>
							<span class="">Toggles LOERIC's accompanying system.</span>
						</label>
						<label class="flex gap-3 justify-between">
							<span class="opacity-60 font-bold ">TRANSPOSE</span>
							<input class="col-span-1" type="number" onchange={transposeChange} bind:value={transpose} min="-12" max="12"/>
						</label>
						<label class="flex gap-3 justify-between">
							<span class="opacity-60 font-bold ">SLOW START</span>
							<input class="col-span-1"type="checkbox" bind:checked={slow_start} onchange={startChange}>
						</label>
						<label class="flex gap-3 justify-between">
							<span class="opacity-60 font-bold ">SLOW END</span>
							<input class="col-span-1"type="checkbox" bind:checked={slow_end} onchange={endChange}>
						</label>
						</label>

					</div>
					<label class="flex flex-col">
						<span class="opacity-60 font-bold">OUTPUT</span>
						<select class="" onchange={outputChange}>
							<option value="synth" selected={musician.midiOut?.startsWith("LOERIC Synth ")}>LOERIC Synth</option>
							<option value="create_out" selected={musician.midiOut?.startsWith("LOERIC out ")}>MIDI Output</option>
							{#each options.outputs as output}
								<option value={output} selected={musician.midiOut === output}>{output}</option>
							{/each}
						</select>
					</label>
				</div>
			</div>
			<div class="flex justify-start w-full p-5 shadow-lg rounded-2xl bg-gray-700 overflow-auto">
				<label class="flex flex-col w-1/4 gap-3">
					<span class="opacity-60 font-bold">INTERACTION</span>
					<select onchange={inputChange}>
						<option value="no_in" selected={musician.midiIn === undefined}>Sliders</option>
						{#each Object.keys(options.audio_inputs) as input}
							<option value={"audioIn:" + options.audio_inputs[input]}
								selected={musician.audioIn === "audioIn:" + options.audio_inputs[input]}>{input}</option>
						{/each}
						{#each options.inputs as input}
							<option value={input} selected={musician.midiIn === input}>{input}</option>
						{/each}
					</select>
				</label>
				{#if musician.controls.length != 0}
					<div class="flex w-auto justify-evenly">
						{#each musician.controls as control}
							<label class="flex flex-col w-24 gap-5">
								<span class="text-center h-12">{control.name}</span>
								<input class="place-self-center" type="range" step="0.01" max="1" min="0" data-control={control.control}
									value={control.value} onchange={controlChange}/>
							</label>
						{/each}
					</div>
				{:else}
					<div class="text-2xl text-center place-self-center w-full">
						No interaction setup.<br> Sit back and have a listen!
					</div>
				{/if}
			</div>
		</div>
	</div>
