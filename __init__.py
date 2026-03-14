"""
ComfyUI Character Prompt Selector
──────────────────────────────────
A custom node that reads character definition YAML files and exposes one
dropdown per category so users can mix-and-match prompt fragments before
passing the combined string to a downstream conditioning node.

Directory resolution order (first wins):
  1. folder_paths "prompt_library" key  →  configured via extra_model_paths.yaml
  2. <node_dir>/prompts/                →  fallback bundled with the node

extra_model_paths.yaml example:
    my_volumes:
        base_path: /workspace
        prompt_library: prompt_library/
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import yaml

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
FOLDER_KEY = "character_prompt_library"
NODE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPTS_DIR = os.path.join(NODE_DIR, "prompts")

_NONE = "(none)"
_NO_FILES = "(no files found)"

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# folder_paths integration
# ──────────────────────────────────────────────────────────────────────────────
try:
    import folder_paths as _fp

    # Register the bundled fallback directory so it's always available.
    _fp.add_model_folder_path(FOLDER_KEY, DEFAULT_PROMPTS_DIR)
    _HAS_FP = True
except ImportError:  # running outside ComfyUI (tests, portability)
    _fp = None  # type: ignore[assignment]
    _HAS_FP = False


def _get_prompt_dirs() -> list[str]:
    """Return all configured prompt-library directories that actually exist."""
    dirs: list[str] = []
    if _HAS_FP:
        try:
            dirs = _fp.get_folder_paths(FOLDER_KEY)
        except KeyError:
            pass
    if not dirs:
        dirs = [DEFAULT_PROMPTS_DIR]
    return [d for d in dirs if os.path.isdir(d)]


def _get_yaml_files() -> dict[str, str]:
    """
    Scan every prompt-library directory for *.yaml / *.yml files.

    Returns {filename: absolute_path}.  When the same filename appears in
    multiple directories only the first occurrence is kept, so users can
    override bundled files by placing a file with the same name in a
    higher-priority directory.
    """
    found: dict[str, str] = {}
    for directory in _get_prompt_dirs():
        try:
            entries = sorted(os.listdir(directory))
        except OSError as exc:
            logger.warning("[CharacterPromptSelector] Cannot list %s: %s", directory, exc)
            continue
        for filename in entries:
            if filename.lower().endswith((".yaml", ".yml")) and filename not in found:
                found[filename] = os.path.join(directory, filename)
    return found


def _load_yaml_safe(filepath: str) -> dict | None:
    """
    Parse a YAML file and return its contents as a dict.

    Returns *None* and logs a warning on any error so the rest of the node
    can degrade gracefully rather than crashing the whole graph.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            logger.warning(
                "[CharacterPromptSelector] %s does not contain a YAML mapping – skipping.",
                filepath,
            )
            return None
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("[CharacterPromptSelector] Failed to load %s: %s", filepath, exc)
        return None


def _build_category_map() -> dict[str, list[str]]:
    """
    Union of all categories and their values from every YAML file.

    Used at node-definition time (INPUT_TYPES) so that *all* categories
    from *all* character files are represented as dropdowns.  At execution
    time only values that belong to the selected character are used.
    """
    categories: dict[str, list[str]] = {}
    for fpath in _get_yaml_files().values():
        data = _load_yaml_safe(fpath)
        if data is None:
            continue
        for key, values in data.items():
            if key == "base" or not isinstance(values, list):
                continue
            bucket = categories.setdefault(key, [])
            for v in values:
                v_str = str(v).strip()
                if v_str and v_str not in bucket:
                    bucket.append(v_str)
    return categories


# ──────────────────────────────────────────────────────────────────────────────
# Node definition
# ──────────────────────────────────────────────────────────────────────────────
class CharacterPromptSelector:
    """
    Loads a character YAML from the prompt_library, presents one dropdown
    per category, and outputs a comma-separated prompt string:

        <base>, <chosen outfit>, <chosen expression>, ...
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        yaml_files = _get_yaml_files()
        file_list = list(yaml_files.keys()) or [_NO_FILES]

        required: dict[str, Any] = {
            "character_file": (file_list,),
        }

        for cat_name, values in _build_category_map().items():
            required[cat_name] = ([_NONE] + values,)

        return {"required": required}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "generate_prompt"
    CATEGORY = "prompt"

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> str:
        """
        Returns a hash of the current YAML-file inventory (names + mtimes).
        ComfyUI uses this to decide whether to skip cached output; the node
        re-executes whenever files are added, removed, or modified.
        """
        yaml_files = _get_yaml_files()
        state_parts: list[str] = []
        for fname, fpath in sorted(yaml_files.items()):
            try:
                mtime = f"{os.path.getmtime(fpath):.6f}"
            except OSError:
                mtime = "?"
            state_parts.append(f"{fname}:{mtime}")
        digest = hashlib.md5(",".join(state_parts).encode()).hexdigest()
        return digest

    # ------------------------------------------------------------------
    def generate_prompt(self, character_file: str, **kwargs: str) -> tuple[str]:
        """
        Build the final prompt string for the selected character.

        Steps:
          1. Re-scan the library directory (picks up newly added files).
          2. Load the selected character YAML.
          3. Prepend the base prompt.
          4. For every category in the YAML, append the selected value
             *only if* it actually appears in that file (silently drops
             stale selections from a previously loaded character).
        """
        yaml_files = _get_yaml_files()

        if character_file == _NO_FILES or character_file not in yaml_files:
            logger.warning(
                "[CharacterPromptSelector] File '%s' not found – returning empty prompt.",
                character_file,
            )
            return ("",)

        data = _load_yaml_safe(yaml_files[character_file])
        if data is None:
            return ("",)

        parts: list[str] = []

        # Base prompt
        base = str(data.get("base", "")).strip()
        if base:
            parts.append(base)

        # Per-category selection
        for key, values in data.items():
            if key == "base" or not isinstance(values, list):
                continue

            selected: str = kwargs.get(key, _NONE)
            if selected == _NONE:
                continue

            # Only include the value if it belongs to this character's file.
            valid_values = {str(v).strip() for v in values}
            if selected in valid_values:
                parts.append(selected)

        return (", ".join(p for p in parts if p),)


# ──────────────────────────────────────────────────────────────────────────────
# ComfyUI registration
# ──────────────────────────────────────────────────────────────────────────────
NODE_CLASS_MAPPINGS = {
    "CharacterPromptSelector": CharacterPromptSelector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CharacterPromptSelector": "Character Prompt Selector",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
