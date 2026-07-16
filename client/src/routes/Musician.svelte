<script lang="ts">
/*
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
*/
	import type {Musician, Options} from "$lib/types";
	import JSONEditorBar from "./JSONEditorBar.svelte";
	import CheckboxOption from "./CheckboxOption.svelte";
	import LOERICOutputEntry from "./LOERICOutputEntry.svelte";

	import { onMount, onDestroy } from "svelte";

	export let musician: Musician
	export let options: Options
	export let apiPut: (action: string, data: any) => Promise<void> = async (_1, _2) => {}
	export let apiUpload: (action: string, form: FormData) => Promise<void> = async (_1, _2) => {}
	export let control_values = {}
	export let intensity_history = []
	import LiveGraph from './LiveGraph.svelte';

	let ws;
	let selected_out = musician.midiOut;

	onMount(() => {
		// Dynamically choose ws or wss based on current page
		const protocol = window.location.protocol === "https:" ? "wss" : "ws";
		const host = window.location.host; // includes hostname and port
		const wsUrl = `${protocol}://${host}/ws/${musician.id}`;

		ws = new WebSocket(wsUrl);
		console.log("Connecting to WebSocket:", wsUrl);

		ws.onopen = () => {
			console.log("WebSocket connected");
		};

		ws.onmessage = (event) => {
			try {
				const data = JSON.parse(event.data);
				//console.log(data);
				if ("intensity" in data){
					//console.log("Received intensity:", data.intensity);
					intensity_history = [...intensity_history, data.intensity];
					if (intensity_history.length > 20) {
						intensity_history = intensity_history.slice(intensity_history.length - 20);
					}
				}
				if ("controls" in data) {
					for (let c in data.controls) {
						control_values[c] = data.controls[c]
					}
				}
			} catch (e) {
				console.error("Error parsing message:", e);
			}
		};

		ws.onclose = () => {
			console.log("WebSocket disconnected");
		};

		ws.onerror = (err) => {
			console.error("WebSocket error:", err);
		};
	});

	onDestroy(() => {
		if (ws) {
			ws.close();
			console.log("WebSocket closed on component destroy");
		}
	});

	$: musician.controls.forEach(c => {
		control_values[c.name] = c.value
	});




	async function inputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		await apiPut("input", {id: musician.id, input: select.value})
	}

	async function outputChange(event: Event) {
		const select = event.target as HTMLSelectElement
		selected_out = select.value
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
		await apiPut("transpose", {id: musician.id, transpose: musician.transpose})
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
		<div class="flex-1 font-semibold">{musician.name}</div> <!--<div class="text-gray-400 font-light">Musician</div>-->
	</div>
	<div class="flex text-lg justify-start gap-5">
		<div class="bg-gray-700 rounded-2xl w-2/3 ">
			<!--<JSONEditorBar json={musician.config} onUpload={uploadConfig}></JSONEditorBar>-->
			<div class="flex flex-col justify-between p-5 gap-3">
			<label class="flex flex-col">
				<span class="text-gray-400 font-bold">INSTRUMENT</span>
				<span class="text-gray-300">Change LOERIC's sound and instrument model.</span>

				<select class="" bind:value={musician.instrument} onchange={instrumentChange}>
					{#each options.instruments as instrument}
						<option value={instrument}>
							{instrument}
						</option>
					{/each}
				</select>
			</label>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<CheckboxOption
					title="DRONES"
					description="Toggle LOERIC's accompanying system."
					bind:_bind={musician.droning}
					_onchange={() => apiPut("drones", { id: musician.id, drones: musician.droning })}
				/>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<label class="flex gap-3 justify-between">
				<div class="flex flex-col">
					<span class="text-gray-400 font-bold">TRANSPOSE</span>
					<span class="text-gray-300">Transpose LOERIC's performance (semitones).</span>
				  </div>
				  <input class="col-span-1" type="number" min="-12" max="12" bind:value={musician.transpose} onchange={transposeChange}/>
				</label>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<CheckboxOption
					title="SLOW START"
					description="Build up speed to selected tempo at performance start."
					bind:_bind={musician.slow_start}
					_onchange={slowStartChange}
				/>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<CheckboxOption
					title="SLOW END"
					description="Slow down from selected tempo at performance end."
					bind:_bind={musician.slow_end}
					_onchange={slowEndChange}
				/>
				<hr class="h-0.5 border-t-0 bg-gray-600" />
				<label class="flex flex-col justify-between">
					<span class="text-gray-400 font-bold">OUTPUT</span>
					<span class="text-gray-300">Choose between built-in sounds or MIDI for external sounds.</span>
					<div class="flex w-full justify-start items-center">
						<el-select class="w-full" onchange={outputChange}>
							<button type="button" class="w-full cursor-default rounded-md bg-transparent py-1.5 pr-2 pl-3 text-left text-white">
								<el-selectedcontent >
									<LOERICOutputEntry name={selected_out} is_synth={selected_out.startsWith("LOERIC Synth")}/>
								</el-selectedcontent>
							</button>
							<el-options anchor="bottom start" popover class="max-h-110 w-(--button-width) overflow-auto rounded-md bg-gray-950 py-1 text-white shadow-lg [--anchor-gap:--spacing(1)] data-leave:transition data-leave:transition-discrete data-leave:duration-100 data-leave:ease-in data-closed:data-leave:opacity-0">
								<el-option value="synth" class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">
									<LOERICOutputEntry name="LOERIC Built-in Synth" is_synth={true}/>
								</el-option>
								<el-option value="create_out"
									class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">
									<LOERICOutputEntry name="LOERIC MIDI Out" is_synth={false}/>
								</el-option>
							{#each options.outputs as output}
								<el-option value={output} class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">
									<LOERICOutputEntry name={output} is_synth={false}/>
								</el-option>
							{/each}
							</el-options>
						</el-select>
					</div>
				</label>
			</div>
		</div>
		<div class="flex flex-col space-y-4 justify-start w-full p-5 shadow-lg rounded-2xl bg-gray-700 overflow-auto">
		<div class="flex flex-col">
				<span class="text-gray-400 font-bold">INTERACTION</span>
				<span class="text-gray-300">Choose how to interact with LOERIC (mouse and sliders, audio input, MIDI).</span>
		</div>
		<div class="flex w-full justify-start items-center">
			<el-select class="w-full" onchange={inputChange}>
				<button type="button" class="w-full cursor-default rounded-md bg-transparent py-1.5 pr-2 pl-3 text-left text-white">
				<el-selectedcontent >
					{#if musician.audioIn === "audioIn:None" && !musician.midiIn}
						<div class="flex items-center gap-3 pr-6">
							<div>
								<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 12.586 19 19"></path><path d="M3.688 3.037a.497.497 0 0 0-.651.651l6.5 15.999a.501.501 0 0 0 .947-.062l1.569-6.083a2 2 0 0 1 1.448-1.479l6.124-1.579a.5.5 0 0 0 .063-.947z"></path></svg>
							</div>
							<div class="text-m">Mouse & Sliders</div>
						</div>
					{:else if !musician.midiIn}
						<div class="flex items-center gap-3 pr-6">
							<div>
								<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" x2="12" y1="19" y2="22"></line></svg>
							</div>
							<div class="text-m">
							{Object.keys(options.audio_inputs).find(key => options.audio_inputs[key] === parseInt(musician.audioIn.replace("audioIn:", "")))}
							</div>
						</div>
					{:else}
						<div class="flex items-center gap-3 pr-6">
							<div>
								<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"></rect><path d="M6 8h4"></path><path d="M14 8h.01"></path><path d="M18 8h.01"></path><path d="M2 12h20"></path><path d="M6 12v4"></path><path d="M10 12v4"></path><path d="M14 12v4"></path><path d="M18 12v4"></path></svg>
							</div>
							<div class="text-m">MIDI: {musician.midiIn}</div>
						</div>
					{/if}
				</el-selectedcontent>
				</button>
					<el-options anchor="bottom start" popover class="max-h-110 w-(--button-width) overflow-auto rounded-md bg-gray-950 py-1 text-white shadow-lg [--anchor-gap:--spacing(1)] data-leave:transition data-leave:transition-discrete data-leave:duration-100 data-leave:ease-in data-closed:data-leave:opacity-0">
						<el-option value="no_in"
						class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">

							<div class="flex items-center gap-3 pr-6">
								<div>
									<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.586 12.586 19 19"></path><path d="M3.688 3.037a.497.497 0 0 0-.651.651l6.5 15.999a.501.501 0 0 0 .947-.062l1.569-6.083a2 2 0 0 1 1.448-1.479l6.124-1.579a.5.5 0 0 0 .063-.947z"></path></svg>
								</div>
								<div class="text-m">Mouse & Sliders</div>
							</div>
						</el-option>
						{#each Object.keys(options.audio_inputs) as input}
							<el-option value={"audioIn:" + options.audio_inputs[input]}
								class="group/option relative block cursor-default py-2 pr-9 pl-3 {input === 'default' ? 'bg-blue-900' : ''} text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">


							<div class="flex justify-between">
								<div class="flex items-center gap-3 pr-6">
										<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" x2="12" y1="19" y2="22"></line></svg>
									<div class="text-m">{input}</div>
									</div>
						{#if input === "default"} <div class="italic text-gray-200">Default microphone</div> {/if}
								</div>
							</el-option>
						{/each}
						{#each options.inputs as input}
							<el-option value={input}

								class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none {input.includes('Launch Control XL') & !input.includes('HUI') ? 'bg-blue-900' : ''} focus:bg-primary group-focus/option:text-white focus:outline-hidden">

							<div class="flex justify-between">
								<div class="flex items-center gap-3 pr-6">
										<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"></rect><path d="M6 8h4"></path><path d="M14 8h.01"></path><path d="M18 8h.01"></path><path d="M2 12h20"></path><path d="M6 12v4"></path><path d="M10 12v4"></path><path d="M14 12v4"></path><path d="M18 12v4"></path></svg>
									<div class="text-m">{input}</div>
									</div>
						{#if input.includes('Launch Control XL') & !input.includes('HUI')} <div class="italic text-gray-200">Supported controller</div> {/if}
								</div>
							</el-option>
						{/each}
					</el-options>
				</el-select>
			</div>
				{#if musician.audioIn != "audioIn:None"}
			<div class="inline-block w-full h-0.5 self-stretch bg-gray-600"></div>
			<div class="flex flex-col justify-between space-y-3">
			<div class="flex flex-col w-1/2">
				<span class="text-gray-400 font-bold">AUDIO SIGNAL</span>
				<span class="text-gray-300">Change how LOERIC interprets your loudness.</span>
			</div>
			  <div class="flex w-auto justify-between items-baseline space-x-2 space-y-1">
				<label class="flex w-full items-center p-2 border border-gray-900 rounded-lg cursor-pointer  {!musician.invert ? 'bg-gray-600 text-white' : 'hover:bg-gray-600'}">
				  <input
					type="radio"
					name="signal"
					value="normal"
					class="mr-2 form-radio text-blue-600"
					checked={!musician.invert}
					onchange={() => apiPut("invert", { id: musician.id, invert: false})} />
				  <div class="flex space-x-2 items-center w-auto justify-evenly">
					<span class="font-bold">NORMAL</span>
					<span class="block text-sm">Loud volume → high intensity</span>
				  </div>
				</label>

				<label class="flex w-full items-center p-2 border border-gray-900 rounded-lg cursor-pointer {musician.invert ? 'bg-gray-600 text-white' : 'hover:bg-gray-600'}">
				  <input
					type="radio"
					name="signal"
					value="inverted"
					class="mr-2 form-radio text-blue-600"
					checked={musician.invert}
					onchange={() => apiPut("invert", { id: musician.id, invert: true})} />
				  <div class="flex space-x-2 items-center w-auto justify-evenly">
					<span class="font-bold">INVERT</span>
					<span class="block text-sm">Low volume → high intensity</span>
				  </div>
				</label>
			  </div>
			  </div>
				{/if}
			{#if musician.controls.length != 0}
				{#if musician.audioIn != "audioIn:None"}
					<label class="flex flex-col w-full space-y-2">
						<span class="text-left w-100">Intensity</span>
						<LiveGraph values={intensity_history}/>
					</label>
				{/if}
			{/if}
			{#if musician.controls.length != 0}
					{#each musician.controls as control}
						{#if musician.audioIn == "audioIn:None" || control.name != "Intensity"}
						<label class="flex w-full items-center">
							<span class="text-left w-100">{control.name}</span>
							<input type="range" step="0.01" max="1" min="0"
							data-control={control.control}
							class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-orange-600 focus:outline-none"
							bind:value={control_values[control.name]} oninput={controlChange}/>
						</label>
						{/if}
					{/each}
			{:else}
				<div class="text-2xl text-center place-self-center w-full">
					No interaction setup.<br> Sit back and have a listen!
				</div>
			{/if}
		</div>
	</div>
</div>
