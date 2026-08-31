import { m, useReducedMotion } from "motion/react";

/**
 * Background watermark: a snake coiled around a medicine vial - the Rod of
 * Asclepius, rebuilt as a vial rather than a staff.
 *
 * The coil is a real helix evaluated at module load rather than hand-drawn
 * curves, because the whole illusion depends on knowing which parts of the body
 * are in front of the vial and which are behind it. With a parametric helix that
 * is just the sign of cos(t), so the path can be split into front and back
 * segments and painted on either side of the glass.
 */

const CX = 150; // horizontal centre of the vial
const RX = 52; // how far the coils swing past the glass
const TOP = 104; // where the topmost coil sits
const TURNS = 3.4;
const PITCH = 58; // vertical drop per full turn
const STEPS = 300;

type Segment = { d: string; front: boolean };

function buildHelix(): Segment[] {
  const segments: Segment[] = [];
  let current: string[] = [];
  let currentFront: boolean | null = null;

  for (let i = 0; i <= STEPS; i++) {
    const t = (i / STEPS) * TURNS * Math.PI * 2;
    const x = CX + RX * Math.sin(t);
    const y = TOP + (t / (Math.PI * 2)) * PITCH;
    const front = Math.cos(t) > 0;

    if (currentFront === null) {
      currentFront = front;
    } else if (front !== currentFront) {
      // Close the run, then start the next one from the same point so the body
      // reads as continuous where it crosses the edge of the glass.
      current.push(`L ${x.toFixed(1)} ${y.toFixed(1)}`);
      segments.push({ d: current.join(" "), front: currentFront });
      current = [];
      currentFront = front;
    }
    current.push(
      `${current.length === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
    );
  }
  if (current.length > 1 && currentFront !== null) {
    segments.push({ d: current.join(" "), front: currentFront });
  }
  return segments;
}

const SEGMENTS = buildHelix();
const FRONT = SEGMENTS.filter((s) => s.front);
const BACK = SEGMENTS.filter((s) => !s.front);

// Head sits at the start of the helix, lifted clear of the rim.
const HEAD = { x: CX, y: TOP - 34 };

const BUBBLES = [
  { cx: 138, cy: 372, r: 3.4, delay: 0 },
  { cx: 158, cy: 388, r: 2.4, delay: 1.7 },
  { cx: 147, cy: 400, r: 4.1, delay: 3.1 },
  { cx: 163, cy: 366, r: 2.0, delay: 4.4 },
];

export default function SnakeVial() {
  const reduced = useReducedMotion();

  // A slow sway sells "alive" far better than anything fast, and at watermark
  // opacity a fast animation would only read as flicker.
  const sway = reduced
    ? {}
    : {
        rotate: [-1.6, 1.6, -1.6],
        transition: { duration: 16, repeat: Infinity, ease: "easeInOut" as const },
      };

  return (
    <div className="landing-snake" aria-hidden="true">
      <svg viewBox="0 0 300 470" fill="none" xmlns="http://www.w3.org/2000/svg">
        <m.g
          style={{ transformOrigin: "150px 260px" }}
          animate={sway}
        >
          {/* Coils that pass behind the glass, dimmed so the vial reads as in front. */}
          <g opacity="0.42">
            {BACK.map((s, i) => (
              <m.path
                key={`b${i}`}
                d={s.d}
                stroke="currentColor"
                strokeWidth="9"
                strokeLinecap="round"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ duration: 1.1, delay: 0.15 * i, ease: "easeInOut" }}
              />
            ))}
          </g>

          {/* The vial. */}
          <g>
            <path
              d="M118 96 h64 v232 a32 32 0 0 1 -64 0 z"
              fill="currentColor"
              fillOpacity="0.07"
              stroke="currentColor"
              strokeWidth="3"
              strokeOpacity="0.55"
            />
            {/* Liquid, with a surface that drifts up and down. */}
            <m.path
              d="M118 300 h64 v28 a32 32 0 0 1 -64 0 z"
              fill="currentColor"
              fillOpacity="0.28"
              animate={reduced ? {} : { y: [0, -7, 0] }}
              transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
            />
            {/* Rim and neck. */}
            <path
              d="M112 96 h76"
              stroke="currentColor"
              strokeWidth="6"
              strokeLinecap="round"
              strokeOpacity="0.8"
            />
            <path
              d="M126 78 h48 v18 h-48 z"
              fill="currentColor"
              fillOpacity="0.16"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeOpacity="0.5"
            />
            {/* Graduation marks. */}
            {[150, 186, 222, 258].map((y) => (
              <path
                key={y}
                d={`M118 ${y} h13`}
                stroke="currentColor"
                strokeWidth="2"
                strokeOpacity="0.4"
              />
            ))}
            {BUBBLES.map((b, i) => (
              <m.circle
                key={i}
                cx={b.cx}
                r={b.r}
                fill="currentColor"
                fillOpacity="0.5"
                initial={{ cy: b.cy, opacity: 0 }}
                animate={
                  reduced
                    ? { cy: b.cy, opacity: 0.5 }
                    : { cy: [b.cy, 312], opacity: [0, 0.75, 0] }
                }
                transition={{
                  duration: 6.5,
                  delay: b.delay,
                  repeat: Infinity,
                  ease: "easeOut",
                }}
              />
            ))}
          </g>

          {/* Coils in front of the glass. */}
          {FRONT.map((s, i) => (
            <m.path
              key={`f${i}`}
              d={s.d}
              stroke="currentColor"
              strokeWidth="10"
              strokeLinecap="round"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 1.1, delay: 0.15 * i + 0.08, ease: "easeInOut" }}
            />
          ))}

          {/* A highlight that runs down the front coils in turn, so the body
              reads as travelling around the vial rather than sitting still. */}
          {!reduced &&
            FRONT.map((s, i) => (
              <m.path
                key={`glow${i}`}
                d={s.d}
                stroke="currentColor"
                strokeWidth="10"
                strokeLinecap="round"
                initial={{ opacity: 0 }}
                animate={{ opacity: [0, 0.85, 0] }}
                transition={{
                  duration: 1.5,
                  delay: 1.4 + i * 0.55,
                  repeat: Infinity,
                  repeatDelay: Math.max(0, FRONT.length * 0.55 - 1.5),
                  ease: "easeInOut",
                }}
              />
            ))}

          {/* Head and tongue. */}
          <m.g
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 1.1, ease: "easeOut" }}
            style={{ transformOrigin: `${HEAD.x}px ${HEAD.y}px` }}
          >
            <path
              d={`M${HEAD.x - 3} ${HEAD.y + 40} C ${HEAD.x - 26} ${HEAD.y + 22} ${HEAD.x - 24} ${HEAD.y - 2} ${HEAD.x - 4} ${HEAD.y}`}
              stroke="currentColor"
              strokeWidth="10"
              strokeLinecap="round"
            />
            <ellipse
              cx={HEAD.x - 6}
              cy={HEAD.y - 3}
              rx="15"
              ry="11"
              fill="currentColor"
              fillOpacity="0.9"
              transform={`rotate(-18 ${HEAD.x - 6} ${HEAD.y - 3})`}
            />
            <circle cx={HEAD.x - 12} cy={HEAD.y - 7} r="2.2" fill="#04211f" />
            <m.path
              d={`M${HEAD.x + 8} ${HEAD.y - 1} l 16 -5 m -16 5 l 15 4`}
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              animate={reduced ? {} : { opacity: [0, 1, 1, 0], x: [0, 4, 4, 0] }}
              transition={{
                duration: 1.2,
                repeat: Infinity,
                repeatDelay: 2.8,
                ease: "easeInOut",
              }}
            />
          </m.g>
        </m.g>
      </svg>
    </div>
  );
}
