# WPML Advanced Translation Editor - Technical Reference

## Editor Structure

The WPML Advanced Translation Editor (ATE) at `e.ate.wpml.org` displays:
- **Left column**: Original language (source text), with field type labels (Title, Paragraph, Heading H2, etc.)
- **Right column**: Translation fields (initially empty with "+" buttons)
- **Top-right**: "Untranslated N" counter with up/down navigation arrows
- **Bottom**: Progress bar (green = translated, red = issues like missing links), "Save to translation memory", "Send feedback", and "Save and Complete" buttons

## Field Types

Fields are labeled by type: Title, Paragraph, Heading (H2), and sometimes grouped under sections like "Quote" or "Main Content". Some fields contain only bullet markers ("·") which are formatting elements that get auto-populated when clicked.

## Opening a Translation Field

- Click the "+" button on the right side of an empty translation field
- The plugin automatically copies the source (English) text into the field
- The field becomes an active TinyMCE rich-text editor inside an iframe

## TinyMCE Editor Interaction

Translation fields use TinyMCE editors embedded in iframes. Direct DOM manipulation or keyboard shortcuts (Ctrl+A) do NOT reliably work within these iframes.

### Correct approach: Use TinyMCE API via JavaScript

```javascript
const editor = tinymce.activeEditor;
if (editor) {
  editor.setContent('<p>Translation text here</p>');
  editor.fire('change');  // CRITICAL: fire change event so WPML registers the edit
}
```

Key points:
- `tinymce.activeEditor` gives access to the currently focused editor
- Always wrap content in `<p>` tags
- Always call `editor.fire('change')` after `setContent()` - without this, WPML may not register the change
- Use Unicode escapes for special characters: `\u00e1` (á), `\u00e9` (é), `\u00ed` (í), `\u00f3` (ó), `\u00fa` (ú), `\u00f1` (ñ), `\u00bf` (¿), `\u00a1` (¡), `\u201c` ("), `\u201d` ("), `\u2122` (™)

### Navigating between fields

Use the "Untranslated" down-arrow button (top-right of the editor) to jump to the next untranslated field. This is more reliable than manually clicking "+" buttons. The arrow auto-opens the field and populates it with source text.

Approximate coordinate for the down-arrow: `[1345, 35]` (may vary by viewport).

## Links in Source Text

Some source paragraphs contain hyperlinks. When a translation field lacks a link present in the source, WPML shows:
- An orange/red circle indicator on the field
- A "Links in the sentence" popup showing the missing link text and URL
- A "Missing required marker" badge
- The progress bar shows red segments for these fields

These warnings do NOT prevent saving but will keep the progress below 100%.

## Saving

- Click "Save and Complete" (bottom-right, green button) to save all translations and mark the job as complete
- Click "Save to translation memory" to save progress without completing
