<script lang="ts">
	import TrackEntry from "./TrackEntry.svelte";
	export let onSelected;
	export let current_track;
	export let track_list;
	export let customized_tracks;

</script>

<el-select onchange={onSelected} class="w-1/2 mt-2 block">
	<button type="button" class="grid w-full cursor-default grid-cols-1 rounded-md bg-transparent py-1.5 pr-2 pl-3 text-left text-white sm:text-sm/6">
		<el-selectedcontent class="col-start-1 row-start-1">

			<TrackEntry trackname={current_track.name.split(".")[0]} extension={current_track.name.split(".")[1]} customized={customized_tracks.includes(current_track.name)} is_selected={false}/>

		</el-selectedcontent>
		<svg viewBox="0 0 16 16" fill="currentColor" data-slot="icon" aria-hidden="true" class="col-start-1 row-start-1 size-5 self-center justify-self-end text-gray-500 sm:size-4">
			<path d="M5.22 10.22a.75.75 0 0 1 1.06 0L8 11.94l1.72-1.72a.75.75 0 1 1 1.06 1.06l-2.25 2.25a.75.75 0 0 1-1.06 0l-2.25-2.25a.75.75 0 0 1 0-1.06ZM10.78 5.78a.75.75 0 0 1-1.06 0L8 4.06 6.28 5.78a.75.75 0 0 1-1.06-1.06l2.25-2.25a.75.75 0 0 1 1.06 0l2.25 2.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" fill-rule="evenodd" />
		</svg>
	</button>

	<el-options anchor="bottom start" popover class="max-h-110 w-(--button-width) overflow-auto rounded-md bg-gray-950 py-1 text-white shadow-lg [--anchor-gap:--spacing(1)] data-leave:transition data-leave:transition-discrete data-leave:duration-100 data-leave:ease-in data-closed:data-leave:opacity-0 sm:text-sm">

		{#each track_list as file}

			<el-option value={file} class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">

				<TrackEntry trackname={file.split(".")[0]} extension={file.split(".")[1]} customized={customized_tracks.includes(file)} is_selected={current_track.name == file}/>
				<span class="text-gren-300 absolute inset-y-0 right-0 flex items-center pr-4 group-not-aria-selected/option:hidden group-focus/option:text-white in-[el-selectedcontent]:hidden">
					<svg viewBox="0 0 20 20" fill="currentColor" data-slot="icon" aria-hidden="true" class="size-5">
						<path d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z" clip-rule="evenodd" fill-rule="evenodd" />
					</svg>
				</span>

			</el-option>
		{/each}
	</el-options>
</el-select>
