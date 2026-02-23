# Ophanic Parser Issues - admin-frontend Test Run

Generated 2026-02-04 from `admin-frontend/src/pages/*.tsx`

## Summary

36 layout diagrams generated. The parser captures basic spatial structure but has significant noise from JSX content bleeding into the output. Issues categorized below with specific examples.

---

## Issue 1: JSX Expression Fragments Leaking Into Boxes

**Severity**: High
**Frequency**: Very common (appears in ~70% of diagrams)

The parser is including JavaScript/JSX expression fragments as if they were layout content.

### Examples

| File | Noise String |
|------|-------------|
| `memory.oph` | `)) ) : ( No memories fou` |
| `selfdevelopment.oph` | `> ))}` |
| `vectors.oph` | `> ))}` |
| `conversations.oph` | `setSearchQuery(e.target.value)}` |
| `wonderland.oph` | `disabled= > Export )}` |
| `chat.oph` | `> msgs ))}` |
| `chat.oph` | `fileInputRef` |
| `soloreflection.oph` | `min\` :` |
| `peopledex.oph` | `setAc` |

### Root Cause Hypothesis

The parser is treating JSX expression boundaries (`{` `}`) as layout boundaries, and capturing partial expression content. Likely happening when:
- Ternary operators: `condition ? <A/> : <B/>`
- Map callbacks: `items.map(item => <Item/>)}`
- Inline handlers: `onClick={() => ...}`

### Suggested Fix

Strip or ignore content between `{` and `}` unless it's a component reference. Alternatively, detect JSX expression patterns and exclude them from text extraction.

---

## Issue 2: Truncated Text Labels

**Severity**: Medium
**Frequency**: Common

Text labels are cut off mid-word, suggesting fixed-width truncation without word boundaries.

### Examples

| File | Truncated | Expected |
|------|-----------|----------|
| `dashboard.oph` | `Dashb` | `Dashboard` |
| `selfdevelopment.oph` | `Self-D` | `Self-Development` |
| `wonderland.oph` | `Curren` | `Current` |
| `conversations.oph` | `Browse conversa` | `Browse conversations` |
| `vectors.oph` | `2D projection o` | `2D projection of...` |
| `peopledex.oph` | `By Typ` | `By Type` |
| `peopledex.oph` | `Al` | `All` |

### Suggested Fix

Either:
1. Truncate at word boundaries with ellipsis (`Dashboard...`)
2. Allow box width to expand to fit label
3. Use abbreviation heuristics for common words

---

## Issue 3: String Literals Appearing as Layout Elements

**Severity**: Medium
**Frequency**: Common

Static text content (descriptions, help text, placeholders) is being rendered as if it were structural layout.

### Examples

| File | String Content |
|------|---------------|
| `register.oph` | `(optional)` - appearing as nested box |
| `register.oph` | `Used to notify you when your account is app` |
| `soloreflection.oph` | `Cass's privat` |
| `wonderland.oph` | `A world made o` |
| `vectors.oph` | `2D projection o` |
| `login.oph` | `Sign` (partial "Sign In") |

### Root Cause Hypothesis

The parser isn't distinguishing between:
- Structural containers (divs, sections with layout meaning)
- Content containers (paragraphs, spans with text content)

### Suggested Fix

Heuristics to identify "content" vs "structure":
- Elements with long text children are likely content
- Elements with only component children are likely structure
- Common content tags: `<p>`, `<span>`, `<label>`, `<h1-6>`

---

## Issue 4: Misaligned/Broken Box Characters

**Severity**: Low-Medium
**Frequency**: Occasional

Some boxes have visual glitches - unmatched corners, overlapping borders.

### Examples

```
# From chat.oph - note the broken nesting:
││ │┌───────────────┐ │ │ │ ││        │ │┌───────│ │ │        ││
```

```
# From dashboard.oph - deep nesting creates confusion:
││┌───────│ │┌────────││
│││┌──────│ ││┌───────││
││││ Dashb│ │││       ││
```

### Suggested Fix

- Limit nesting depth (3-4 levels max)
- Simplify deeply nested structures into single labeled boxes
- Add validation pass to ensure box character matching

---

## Issue 5: Component Reference Inconsistency

**Severity**: Medium
**Frequency**: Common

Some components get the `◆` marker, others don't. Inconsistent detection.

### Correctly Detected

- `◆SchedulePanel` (dashboard.oph)
- `◆ChatWidget` (dashboard.oph)
- `◆Link` (login.oph)
- `◆GenesisNotification` (layout)
- `◆Outlet` (layout)

### Missed (No ◆ Marker)

- `Conversations` - just text, should be `◆Conversations` or ignored
- `Statistics` - text, not marked as component
- `Sessions` - text, not marked as component

### Suggested Fix

Detect PascalCase identifiers that appear as JSX element names and mark with `◆`. Distinguish from:
- HTML elements (lowercase)
- Text content (sentence case, spaces)

---

## Issue 6: Empty/Ghost Boxes

**Severity**: Low
**Frequency**: Common

Many diagrams have large empty rectangular regions that add noise without information.

### Example

```
# homepage.oph - almost entirely empty boxes:
│ │ ┌────────────────────────────────┐ ││
│ │ │                                │ ││
│ │ └────────────────────────────────┘ ││
│ │ ┌────────────────────────────────┐ ││
│ │ │                                │ ││
│ │ └────────────────────────────────┘ ││
```

### Suggested Fix

- Collapse empty containers
- Only render boxes that have meaningful content or component references
- Add `--collapse-empty` flag option

---

## Issue 7: Event Handler Code Appearing

**Severity**: High
**Frequency**: Occasional

JavaScript callback code is appearing in the output.

### Examples

| File | Handler Code |
|------|-------------|
| `conversations.oph` | `setSearchQuery(e.target.value)}` |
| `peopledex.oph` | `setAc` (partial `setActiveTab`) |

### Suggested Fix

Same root cause as Issue 1. Strip all `{...}` expression content that isn't a component instantiation.

---

## Recommendations for Parser Improvements

### Priority 1 (Fixes most noise)
1. **Strip JSX expressions**: Remove all `{...}` content except component references
2. **Ignore text-heavy elements**: Skip `<p>`, `<span>`, `<label>` content

### Priority 2 (Improves readability)
3. **Word-boundary truncation**: Don't cut labels mid-word
4. **Collapse empty boxes**: Remove visual noise from empty containers
5. **Consistent component marking**: All PascalCase JSX elements get `◆`

### Priority 3 (Polish)
6. **Limit nesting depth**: Flatten deeply nested structures
7. **Box validation**: Ensure all corners match

---

## Test Files for Regression

Good test cases that exercise various issues:

| File | Tests |
|------|-------|
| `chat.oph` | Complex nesting, multiple components |
| `register.oph` | Form fields, help text, string literals |
| `dashboard.oph` | Component references, three-column layout |
| `conversations.oph` | Event handlers, search input |
| `homepage.oph` | Empty boxes |

---

## Positive Notes

Things the parser got right:

1. **Basic three-column detection** - Dashboard correctly shows SchedulePanel | Main | ChatWidget
2. **Component references** - When detected, the `◆` markers are helpful
3. **Header detection** - Page titles often correctly placed at top-left
4. **Proportional widths** - Column widths roughly proportional to actual layout

The foundation is solid. Main work is filtering out non-structural content.
