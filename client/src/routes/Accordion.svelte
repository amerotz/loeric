<script>
	export let open = false;
	import {slide} from 'svelte/transition';

	export function toggleOpen() {
		open = !open;
	}
</script>

<div class="flex flex-col">
	<div class="flex">
		<button class="flex flex-1" onclick={toggleOpen}>
			<slot name="head">Config</slot>
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
