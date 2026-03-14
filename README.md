# comfyui-character-prompt-selector

A ComfyUI custom node that loads character definition YAML files and lets you
compose a final prompt via per-category dropdowns — one dropdown per key found
in your YAML files (outfits, expressions, poses, or anything else you define).

## Features

- **Dynamic categories** — categories come from your YAML keys; no hardcoding needed
- **Multi-file library** — point the node at any directory; all `.yaml` / `.yml`
  files become entries in the character dropdown
- **Live rescan** — the node detects new or modified YAML files without a ComfyUI
  restart (cache is keyed to file names + modification times)
- **Graceful degradation** — malformed or missing files produce a warning in the
  ComfyUI log and return an empty string instead of crashing the graph
- **Standard integration** — the prompt-library directory is registered via
  ComfyUI's `folder_paths` mechanism, the same way checkpoint and LoRA
  folders are handled; configure it once in `extra_model_paths.yaml` and it
  works everywhere — local installs, RunPod network volumes, etc.

---

## Installation

### Via ComfyUI Manager (recommended)
Search for **"Character Prompt Selector"** and click Install.

### Manual
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/suffle/comfyui-character-prompt-selector.git
```
Restart ComfyUI.  The node appears under the **prompt** category.

---

## YAML format

```yaml
# Every key except "base" becomes a dropdown in the node.
base: "1girl, long silver hair, blue eyes, masterpiece"

outfits:
  - "red cocktail dress, heels"
  - "gothic lolita, black dress"

expressions:
  - "smile, happy"
  - "serious, cold expression"

poses:
  - "standing, arms crossed"
  - "sitting, legs crossed"
```

- **`base`** — prepended to every output regardless of other selections
- **Any other key** — becomes a dropdown; pick `(none)` to omit that category

Category names can be anything valid as a Python identifier
(`outfits`, `hair_styles`, `backgrounds`, …).

---

## Configuring the prompt-library directory

### Option A — `extra_model_paths.yaml` (recommended)

Add a `character_prompt_library` entry to your `extra_model_paths.yaml`.  The path is
resolved relative to `base_path`, exactly like checkpoints or LoRAs:

```yaml
# ComfyUI/extra_model_paths.yaml
comfyui:
    base_path: /workspace          # absolute, or relative to this file
    character_prompt_library: prompt_library/
```

```yaml
# RunPod / network volume example
runpod_volume:
    base_path: /workspace
    checkpoints: models/checkpoints/
    loras: models/loras/
    character_prompt_library: prompt_library/   # ← add this line
```

Restart ComfyUI once after editing the file.

### Option B — bundled `prompts/` folder (zero-config fallback)

Drop your YAML files into `custom_nodes/comfyui-character-prompt-selector/prompts/`.
No configuration required; this directory is always searched as the last fallback.

---

## How it works

Because ComfyUI evaluates `INPUT_TYPES` once at startup, the node builds its
dropdown lists at that point by **unioning all categories and values** from
every YAML file it finds.  At execution time it loads the selected character
file and silently discards any dropdown selection that does not belong to that
character's file — so switching characters never passes stale values downstream.

---

## Output

| Name | Type | Description |
|------|------|-------------|
| `prompt` | `STRING` | `<base>, <category 1 selection>, <category 2 selection>, …` |

---

## License

MIT
