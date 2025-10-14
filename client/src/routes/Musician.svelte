<script lang="ts">
	import type {Musician, Options} from "$lib/types";
	import JSONEditorBar from "./JSONEditorBar.svelte";

	export let musician: Musician
	export let options: Options
	export let apiPut: (action: string, data: any) => Promise<void> = async (_1, _2) => {}
	export let apiUpload: (action: string, form: FormData) => Promise<void> = async (_1, _2) => {}

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

<div class="flex px-1">
	<div class="flex-1 font-semibold">{musician.name}</div>
	<div class="opacity-60 font-light">Musician</div>
</div>
	<!--<JSONEditorBar json={musician.config} onUpload={uploadConfig}></JSONEditorBar>-->
<label class="flex flex-col">
	<span class="text-m px-1 opacity-60">Instrument</span>
	<select onchange={instrumentChange}>
		{#each options.instruments as instrument}
			<option value={instrument}
			        selected={musician.instrument === instrument}>{instrument}</option>
		{/each}
	</select>
</label>
<label class="flex flex-col">
	<span class="text-m px-1 opacity-60">Output</span>
	<select onchange={outputChange}>
		<option value="synth" selected={musician.midiOut?.startsWith("LOERIC Synth ")}>LOERIC
			Synth
		</option>
		<option value="create_out" selected={musician.midiOut?.startsWith("LOERIC out ")}>MIDI
			Output
		</option>
		{#each options.outputs as output}
			<option value={output} selected={musician.midiOut === output}>{output}</option>
		{/each}
	</select>
</label>
<label class="flex flex-col">
	<span class="text-m px-1 opacity-60">Input</span>
	<select onchange={inputChange}>
		<option value="no_in" selected={musician.midiIn === undefined}>None</option>
		{#each Object.keys(options.audio_inputs) as input}
			<option value={"audioIn:" + options.audio_inputs[input]}
			        selected={musician.midiIn === "audioIn:" + options.audio_inputs[input]}>{input}</option>
		{/each}
		{#each options.inputs as input}
			<option value={input} selected={musician.midiIn === input}>{input}</option>
		{/each}
	</select>
</label>
<div class="flex py-2 justify-between">
	{#each musician.controls as control}
		<label class="flex flex-col w-24 gap-5">
			<span class="text-xs text-center h-12">{control.name}</span>
			<input class="place-self-center" type="range" step="0.01" max="1" min="0" data-control={control.control}
			       value={control.value} onchange={controlChange}/>
		</label>
	{/each}
</div>
