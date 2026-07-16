<script lang="ts">
/*
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
*/
	import {type Content, JSONEditor, Mode} from "svelte-jsoneditor"
	import Accordion from "./Accordion.svelte"
	import FileUpload from "./FileUpload.svelte"

	let {
		json,
		onUpload = async () => {},
		text
	}: {
		json: any,
		onUpload: (form: FormData) => Promise<void>
	} = $props()
	let content: Content = $derived({
		json: json
	})

	let mode = $state(Mode.tree)

	async function handleChange(updatedContent: Content, _: Content, _status: any) {
		const json = updatedContent?.json
		if (json) {
			const formData = new FormData()
			const newContent = new Blob([JSON.stringify(json)], {type: "application/json"})
			formData.append('upload', newContent)
			await onUpload(formData)
		}
	}
</script>

<style lang="postcss">
	@import 'svelte-jsoneditor/themes/jse-theme-dark.css';

	.jse-theme-dark {
		--jse-main-border: 0 solid #000;
		--jse-background-color: #030712;
		--jse-key-color: #99a1af;
		--jse-delimiter-color: #6a7282;
    	--jse-font-size-mono: 1rem;
  }
</style>

<Accordion text={text}>
	<div class="jse-theme-dark flex flex-col">
		<div class="flex text-m">
			<button onclick={() => mode = Mode.text} class="material-symbols-outlined !text-base p-1" title="Edit Text">
				text_snippet
			</button>
			<button onclick={() => mode = Mode.tree} class="material-symbols-outlined !text-base p-1" title="Edit Tree">
				account_tree
			</button>

			<FileUpload accepted="json, application/json" onUpload={onUpload}>
				<span class="material-symbols-outlined !text-base p-1">upload</span>
			</FileUpload>
		</div>
		<JSONEditor mode={mode} content={content} mainMenuBar={false} navigationBar={false} statusBar={false} onChange={handleChange}/>
	</div>
</Accordion>
