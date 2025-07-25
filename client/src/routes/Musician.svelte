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
		background: url("../assets/fader_knob.svg");
		background-size: contain;
		cursor: pointer;
	}
</style>

<div class="flex px-1">
	<div class="flex-1 font-semibold">{musician.name}</div>
	<div class="opacity-60 font-light">Musician</div>
</div>
<JSONEditorBar json={musician.config} onUpload={uploadConfig}></JSONEditorBar>
<label class="flex flex-col">
	<span class="text-xs px-1 opacity-60">Instrument</span>
	<select onchange={instrumentChange}>
		{#each options.instruments as instrument}
			<option value={instrument}
			        selected={musician.instrument === instrument}>{instrument}</option>
		{/each}
	</select>
</label>
<label class="flex flex-col">
	<span class="text-xs px-1 opacity-60">Output</span>
	<select onchange={outputChange}>
		<option value="synth" selected={musician.midiOut?.startsWith("Loeric Synth ")}>Loeric
			Synth
		</option>
		<option value="create_out" selected={musician.midiOut?.startsWith("Loeric Out ")}>Midi
			Output
		</option>
		{#each options.outputs as output}
			<option value={output} selected={musician.midiOut === output}>{output}</option>
		{/each}
	</select>
</label>
<label class="flex flex-col">
	<span class="text-xs px-1 opacity-60">Input</span>
	<select onchange={inputChange}>
		<option value="no_in" selected={musician.midiIn === undefined}>None</option>
		{#each Object.keys(options.audio) as input}
			<option value={"audioIn:" + options.audio[input]}
			        selected={musician.midiIn === "audioIn:" + options.audio[input]}>{input}</option>
		{/each}
		{#each options.inputs as input}
			<option value={input} selected={musician.midiIn === input}>{input}</option>
		{/each}
	</select>
</label>
<div class="flex py-2 self-center">
	{#each musician.controls as control}
		<label class="flex flex-col items-center gap-1">
			<span class="text-xs text-center">{control.name}</span>
			<input type="range" max="127" min="0" data-control={control.control}
			       value={control.value} onchange={controlChange}/>
		</label>
	{/each}
</div>
