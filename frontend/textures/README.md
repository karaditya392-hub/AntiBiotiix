# Manus design textures

Two textures from the Manus redesign are referenced by the stylesheets but were
not available in the handoff. Drop them in here with these exact filenames and
they will be picked up with no code change:

| File | Used by | Effect |
| --- | --- | --- |
| `console-texture.png` | `src/styles/legacy.css` (body background) | Console/clinical-interface texture, under a 0.92-alpha wash |
| `evidence-pattern.png` | `src/styles/landing.css` (`.landing-final-cta::after`) | Evidence texture at `opacity: .12`, `mix-blend-mode: screen` |

They are served from `/static/textures/`. Until they exist the surfaces render as
flat colour: the `background-image` layer simply resolves to nothing and every
other declaration still applies, so nothing breaks and no substitute is invented.
