---
name: wpml-translation-editor
description: |
  **WPML Translation Pasting**: Paste translations from a plain-text file into the WPML Advanced Translation Editor (ATE) via browser automation.
  - MANDATORY TRIGGERS: WPML, translation editor, ATE, paste translation, translation pasting, WPML translation, translate post, translate page, translation file
  - Use when the user provides a .txt translation file and has the WPML ATE open in the browser
  - Handles clicking fields, replacing auto-filled source text with correct translations via TinyMCE API, and navigating through all untranslated segments
---

# WPML Translation Editor - Paste Translations

Paste translations from a user-provided plain-text file into the WPML Advanced Translation Editor (ATE) open in the browser. Click each field, replace auto-populated source text with the correct translation via TinyMCE API, navigate through all segments until complete.

## Prerequisites

1. User uploads a `.txt` file containing the full translation (plain text, no HTML)
2. User has the WPML ATE open in Chrome (url contains `e.ate.wpml.org`)
3. Claude in Chrome browser tools are available

## Workflow

1. **Read the translation file** and parse its structure
2. **Get browser context** (`tabs_context_mcp`) and screenshot to verify ATE is open
3. **Verify source-translation match**: Compare the article title/content visible in the ATE against the translation file. **If they don't match, STOP and alert the user** — never paste the wrong translation into the wrong article
4. **Parse the translation** into ordered segments matching the ATE field structure (title, paragraphs, headings, quotes)
5. **For each untranslated field**:
   - Click the "Untranslated" down-arrow (top-right, ~`[1345, 35]`) to navigate to the next empty field
   - Confirm the source text on the left matches the expected segment
   - Replace content via TinyMCE API (see below)
   - Bullet marker fields ("·") auto-populate — skip them
6. **Flag link warnings** at the end: list any source hyperlinks absent from the translation
7. **Verify** "Untranslated: 0" and report final status to user

## Critical Rules

- **NEVER modify the translation text.** Paste exactly what the file contains.
- **ALWAYS verify** the source article matches the translation file before starting.
- **ALWAYS confirm** each segment goes into the correct field by checking the left-side source text.

## TinyMCE Field Replacement

The ATE uses TinyMCE editors inside iframes. Standard keyboard shortcuts (Ctrl+A, type) do NOT work reliably inside these iframes. Always use JavaScript:

```javascript
const editor = tinymce.activeEditor;
editor.setContent('<p>Translation text here</p>');
editor.fire('change');  // REQUIRED — without this WPML won't register the edit
```

Use Unicode escapes for accented/special characters: `\u00e1` (á), `\u00e9` (é), `\u00ed` (í), `\u00f3` (ó), `\u00fa` (ú), `\u00f1` (ñ), `\u00bf` (¿), `\u00a1` (¡), `\u201c` (\u201c), `\u201d` (\u201d), `\u2122` (™).

For full technical details, see [references/wpml-tinymce-interaction.md](references/wpml-tinymce-interaction.md).

## Link Warnings

Source text may contain hyperlinks not present in the plain-text translation. WPML shows "Missing required marker" warnings and orange indicators for these. After completing all fields, report the affected fields and link URLs so the user can add them manually.