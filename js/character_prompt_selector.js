/**
 * Character Prompt Selector — ComfyUI frontend extension
 *
 * When a CharacterPromptSelector node is present in the graph this extension:
 *   - Hooks the "character_file" combo so that whenever the user picks a
 *     different YAML file the category dropdowns are immediately narrowed to
 *     only the values that exist in that file.  Categories absent from the
 *     chosen file are reset to "(none)".
 *   - Adds a "⟳  Reload Library" button that re-scans the prompt-library
 *     directory on the server and refreshes both the file list and the
 *     category dropdowns without requiring a full browser reload.
 */

import { app } from "../../scripts/app.js";

const NODE_TYPE   = "CharacterPromptSelector";
const NONE_OPTION = "(none)";
const NO_FILES    = "(no files found)";
const API         = "/character_prompt_selector";

// ─── helpers ──────────────────────────────────────────────────────────────────

async function apiFetch(path) {
    try {
        const resp = await fetch(API + path);
        if (!resp.ok) return null;
        return await resp.json();
    } catch {
        return null;
    }
}

/**
 * Narrow every category combo on `node` to the values provided by `data`.
 * Categories absent from the file are set to [(none)]; stale selected values
 * are reset to (none) automatically.
 */
function applyCategoryData(node, data) {
    if (!data?.categories) return;
    const { categories } = data;

    for (const widget of node.widgets) {
        if (widget.name === "character_file") continue;
        if (widget.type !== "combo") continue;

        const fileValues = categories[widget.name];
        const newOptions = fileValues?.length
            ? [NONE_OPTION, ...fileValues]
            : [NONE_OPTION];

        widget.options.values = newOptions;

        // Reset selection if it no longer belongs to this file's values.
        if (!newOptions.includes(widget.value)) {
            widget.value = NONE_OPTION;
        }
    }
}

// ─── extension ────────────────────────────────────────────────────────────────

app.registerExtension({
    name: "Suffle.CharacterPromptSelector",

    async nodeCreated(node) {
        if (node.comfyClass !== NODE_TYPE) return;

        const fileWidget = node.widgets?.find(w => w.name === "character_file");
        if (!fileWidget) return;

        // ── 1. React to file-selector changes ──────────────────────────────
        const origCallback = fileWidget.callback;
        fileWidget.callback = async function (value, ...rest) {
            // Let ComfyUI / LiteGraph handle its own bookkeeping first.
            origCallback?.call(this, value, ...rest);

            const data = await apiFetch(
                `/categories?file=${encodeURIComponent(value)}`
            );
            applyCategoryData(node, data);
            app.graph.setDirtyCanvas(true, true);
        };

        // ── 2. Reload Library button ────────────────────────────────────────
        node.addWidget("button", "⟳  Reload Library", null, async () => {
            const filesData = await apiFetch("/files");
            if (!filesData?.files) return;

            // Refresh the file-selector combo.
            const files = filesData.files.length ? filesData.files : [NO_FILES];
            fileWidget.options.values = files;

            // Keep the current selection if it still exists, otherwise fall
            // back to the first item in the refreshed list.
            if (!files.includes(fileWidget.value)) {
                fileWidget.value = files[0];
            }

            // Re-apply category filters for the (possibly new) selection.
            const catData = await apiFetch(
                `/categories?file=${encodeURIComponent(fileWidget.value)}`
            );
            applyCategoryData(node, catData);
            app.graph.setDirtyCanvas(true, true);
        });

        // ── 3. Populate correctly on initial load / workflow restore ────────
        const initialFile = fileWidget.value;
        if (initialFile && initialFile !== NO_FILES) {
            const data = await apiFetch(
                `/categories?file=${encodeURIComponent(initialFile)}`
            );
            applyCategoryData(node, data);
        }
    },
});
