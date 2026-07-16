<script type="ts">
/*
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
*/
	export let title;
	export let description;
	export let _bind;
	export let _onchange;

	$: _bind
</script>

<label class="flex gap-3 justify-between">
 <div class="flex flex-col">
		<span class="text-gray-400 font-bold">{title}</span>
		<span class="text-gray-300">{description}</span>
	</div>
	<input 	class="col-span-1 rounded-md border-gray-300 text-orange-600 transition"
			type="checkbox"
			bind:checked={_bind}
			onchange={_onchange()}
	/>
</label>
