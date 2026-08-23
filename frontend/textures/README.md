# Manus design textures

Both textures from the Manus redesign are present and served from
`/static/textures/`.

| File | Source | Used by | Effect |
| --- | --- | --- | --- |
| `console-texture.jpg` | 1600x900 | `src/styles/legacy.css` (body background) | Console/clinical-interface blueprint, under a 0.92-alpha wash so it reads as barely-there grain |
| `evidence-pattern.jpg` | 1600x1066 | `src/styles/landing.css` (`.landing-final-cta::after`) | Evidence texture at `opacity: .12`, `mix-blend-mode: screen` |

They are JPEG rather than PNG because both are dark photographic gradients with
no transparency, so JPEG is the correct format and roughly a third of the size.
The stylesheets reference the real extension; there is no `.png` indirection.
