<script lang="ts">
	import type {Musician, Options} from "$lib/types";
	import JSONEditorBar from "./JSONEditorBar.svelte";


	export let musician: Musician
	export let options: Options
	export let apiPut: (action: string, data: any) => Promise<void> = async (_1, _2) => {}
	export let apiUpload: (action: string, form: FormData) => Promise<void> = async (_1, _2) => {}
	export let transpose = musician.transpose
	export let control_values = {}

	$: transpose = musician.transpose

	$: musician.controls.forEach(c => {
		control_values[c.name] = c.value
	});

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

	async function droningChange() {
		await apiPut("droning", {
			id: musician.id,
			droning: musician.droning
		})
	}

	async function slowStartChange() {
		await apiPut("slow_start", {
			id: musician.id,
			slow_start: musician.slow_start
		})
	}

	async function slowEndChange() {
		await apiPut("slow_end", {
			id: musician.id,
			slow_end: musician.slow_end
		})
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
		<div class="bg-gray-700 rounded-2xl w-2/3 ">
			<!--<JSONEditorBar json={musician.config} onUpload={uploadConfig}></JSONEditorBar>-->
			<div class="flex flex-col justify-between p-5 gap-3">
			<label class="flex flex-col">
				<span class="opacity-60 font-bold">INSTRUMENT</span>
				<span class="opacity-80">Change LOERIC's sound and instrument model.</span>

				<select class="" bind:value={musician.instrument} onchange={instrumentChange}>
					{#each options.instruments as instrument}
						<option value={instrument}>
							{instrument}
						</option>
					{/each}
				</select>
			</label>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<label class="flex gap-3 justify-between">
					<div class="flex flex-col">
						<span class="opacity-60 font-bold">DRONES</span>
						<span class="opacity-80">Toggle LOERIC's accompanying system.</span>
					</div>
					<input class="col-span-1" type="checkbox" bind:checked={musician.droning} onchange={() => apiPut("drones", { id: musician.id, drones: musician.droning })} />
				</label>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<label class="flex gap-3 justify-between">
				<div class="flex flex-col">
					<span class="opacity-60 font-bold">TRANSPOSE</span>
					<span class="opacity-80">Transpose LOERIC's performance (semitones).</span>
				  </div>
				  <input class="col-span-1" type="number" min="-12" max="12" bind:value={transpose} onchange={transposeChange}/>
				</label>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<label class="flex gap-3 justify-between">
					<div class="flex flex-col">
						<span class="opacity-60 font-bold ">SLOW START</span>
						<span class="opacity-80">Build up speed to selected tempo at performance start.</span>
					</div>
					<input class="col-span-1" type="checkbox" bind:checked={musician.slow_start} onchange={slowStartChange} />
				</label>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<label class="flex gap-3 justify-between">
					<div class="flex flex-col">
						<span class="opacity-60 font-bold ">SLOW END</span>
						<span class="opacity-80">Slow down from selected tempo at performance end.</span>
					</div>
					<input class="col-span-1" type="checkbox" bind:checked={musician.slow_end} onchange={slowEndChange} />

				</label>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<label class="flex flex-col justify-between">
					<span class="opacity-60 font-bold">OUTPUT</span>
					<span class="opacity-80">Choose between built-in sounds or MIDI for external sounds.</span>
					<select class="mt-3" onchange={outputChange}>
						<option value="synth" selected={musician.midiOut?.startsWith("LOERIC Synth ")}>LOERIC Built-In Synth</option>
						<option value="create_out" selected={musician.midiOut?.startsWith("LOERIC out ")}>LOERIC MIDI Output</option>
						{#each options.outputs as output}
							<option value={output} selected={musician.midiOut === output}>{output}</option>
						{/each}
					</select>
				</label>
			</div>
		</div>
		<div class="flex gap-3 justify-start w-full p-5 shadow-lg rounded-2xl bg-gray-700 overflow-auto">
			<label class="flex flex-col w-1/4 gap-3">
				<span class="opacity-60 font-bold">INTERACTION</span>
				<span class="opacity-80">Choose how to interact with LOERIC (sliders, audio input, MIDI).</span>
				<el-select onchange={inputChange}>
					<button type="button" class="grid w-full cursor-default grid-cols-1 rounded-md bg-transparent py-1.5 pr-2 pl-3 text-left text-white">
						<el-selectedcontent value="no_in" selected={musician.midiIn === "no_in"}>
							<div class="flex gap-3 pr-6">
								<div>
									<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 12.586 19 19"></path><path d="M3.688 3.037a.497.497 0 0 0-.651.651l6.5 15.999a.501.501 0 0 0 .947-.062l1.569-6.083a2 2 0 0 1 1.448-1.479l6.124-1.579a.5.5 0 0 0 .063-.947z"></path></svg>
								</div>
								<div class="text-m">Mouse</div>
							</div>
						</el-selectedcontent>
					</button>
					<el-options anchor="bottom start" popover class="max-h-110 w-(--button-width) overflow-auto rounded-md bg-gray-950 py-1 text-white shadow-lg [--anchor-gap:--spacing(1)] data-leave:transition data-leave:transition-discrete data-leave:duration-100 data-leave:ease-in data-closed:data-leave:opacity-0">
						<el-option value="no_in" class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">

							<div class="flex gap-3 pr-6">
								<div>
									<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 12.586 19 19"></path><path d="M3.688 3.037a.497.497 0 0 0-.651.651l6.5 15.999a.501.501 0 0 0 .947-.062l1.569-6.083a2 2 0 0 1 1.448-1.479l6.124-1.579a.5.5 0 0 0 .063-.947z"></path></svg>
								</div>
								<div class="text-m">Mouse</div>
							</div>
						</el-option>
						{#each Object.keys(options.audio_inputs) as input}
							<el-option value={"audioIn:" + options.audio_inputs[input]}
								class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">


								<div class="flex gap-3 pr-6">
									<div>
										<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" x2="12" y1="19" y2="22"></line></svg>
									</div>
									<div class="text-m">{input}</div>
								</div>
							</el-option>
						{/each}
						{#each options.inputs as input}
							<el-option value={input}

								class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">

								<div class="flex gap-3 pr-6">
									<div>
										<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"></rect><path d="M6 8h4"></path><path d="M14 8h.01"></path><path d="M18 8h.01"></path><path d="M2 12h20"></path><path d="M6 12v4"></path><path d="M10 12v4"></path><path d="M14 12v4"></path><path d="M18 12v4"></path></svg>
									</div>
									<div class="text-m">{input}</div>
								</div>
							</el-option>
						{/each}
					</el-options>
				</el-select>
			</label>
			<div class="inline-block h-full w-0.5 self-stretch bg-gray-600"></div>
			{#if musician.controls.length != 0}
				<div class="flex w-auto justify-evenly">
					{#each musician.controls as control}
						<label class="flex flex-col w-24 gap-5">
							<span class="text-center h-12">{control.name}</span>
							<input class="place-self-center" type="range" step="0.01" max="1" min="0"
							data-control={control.control}
							bind:value={control_values[control.name]} oninput={controlChange}/>
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
