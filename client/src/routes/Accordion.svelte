<script>
/*
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
*/
	export let open = false;
	export let text;
	import {slide} from 'svelte/transition';

	export function toggleOpen() {
		open = !open;
	}
</script>

<div class="flex flex-col ">
	<div class="flex">
		<button class="flex flex-1" onclick={toggleOpen}>
			<slot name="head">{text}</slot>
			<span class="material-symbols-outlined flex-1 text-end">
				{#if open}
					keyboard_arrow_up
				{:else}
					keyboard_arrow_down
				{/if}
			</span>
		</button>
	</div>

	{#if open}
		<div transition:slide>
			<slot></slot>
		</div>
	{/if}
</div>
