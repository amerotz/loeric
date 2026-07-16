<script>
/*
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
*/
	export let onChange;
	export let dropdown_entry;
	export let options;
</script>
<div class="flex w-full justify-start items-center">
	<el-select class="w-full" onchange={onchange}>
		<button type="button" class="w-full cursor-default rounded-md bg-transparent py-1.5 pr-2 pl-3 text-left text-white">
			<el-selectedcontent >
				<dropdown_entry/>
			</el-selectedcontent>
		</button>
		<el-options anchor="bottom start" popover class="max-h-110 w-(--button-width) overflow-auto rounded-md bg-gray-950 py-1 text-white shadow-lg [--anchor-gap:--spacing(1)] data-leave:transition data-leave:transition-discrete data-leave:duration-100 data-leave:ease-in data-closed:data-leave:opacity-0">
		{#each options as item}
			<el-option value={item} class="group/option relative block cursor-default py-2 pr-9 pl-3 text-white select-none focus:bg-primary group-focus/option:text-white focus:outline-hidden">
				<dropdown_entry/>
			</el-option>
		{/each}
		</el-options>
	</el-select>
</div>
