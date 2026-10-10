import { useEffect, useRef } from 'react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

export type BackdropMood = 'idle' | 'scanning' | 'working' | 'review' | 'success' | 'error'

/** Accent per mood: the aurora tint, and how many pulses are red (failing)
 * before they cross a checkpoint and turn green (verified). */
const MOODS: Record<BackdropMood, { aurora: string; aurora2: string; failShare: number; speed: number }> = {
  idle: { aurora: '34,197,94', aurora2: '34,211,238', failShare: 0.55, speed: 1 },
  scanning: { aurora: '34,211,238', aurora2: '34,197,94', failShare: 0.7, speed: 1.3 },
  working: { aurora: '245,158,11', aurora2: '34,211,238', failShare: 0.75, speed: 1.6 },
  review: { aurora: '245,158,11', aurora2: '34,197,94', failShare: 0.3, speed: 0.8 },
  success: { aurora: '34,197,94', aurora2: '134,239,172', failShare: 0.1, speed: 1 },
  error: { aurora: '239,68,68', aurora2: '245,158,11', failShare: 1, speed: 0.7 },
}

const GRID = 56
const FAIL = [239, 68, 68]
const PASS = [34, 197, 94]
const SCAN = [34, 211, 238]

interface Pulse {
  horizontal: boolean
  lane: number
  pos: number
  speed: number
  checkpoint: number // where it turns green, in px along the lane
  startsFailing: boolean
  flash: number // 0..1 burst when it turns green
  tail: number
}

function spawn(width: number, height: number, failShare: number, fresh = false): Pulse {
  const horizontal = Math.random() < 0.6
  const length = horizontal ? width : height
  const lanes = Math.max(1, Math.floor((horizontal ? height : width) / GRID))
  return {
    horizontal,
    lane: (1 + Math.floor(Math.random() * lanes)) * GRID,
    pos: fresh ? Math.random() * length : -40,
    speed: 0.6 + Math.random() * 1.6,
    checkpoint: length * (0.25 + Math.random() * 0.5),
    startsFailing: Math.random() < failShare,
    flash: 0,
    tail: 40 + Math.random() * 90,
  }
}

/** Full-screen animated background: a circuit grid with test signals
 * travelling along it. Red pulses cross a checkpoint and turn green, which is
 * the whole product in one picture. Purely decorative. */
export function Backdrop({ mood = 'idle' }: { mood?: BackdropMood }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const moodRef = useRef(mood)
  const reducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    moodRef.current = mood
  }, [mood])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx || reducedMotion) return

    let width = 0
    let height = 0
    let pulses: Pulse[] = []
    let frame = 0
    let raf = 0

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = width * dpr
      canvas.height = height * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.round(Math.min(34, (width * height) / 42000))
      pulses = Array.from({ length: count }, () => spawn(width, height, MOODS[moodRef.current].failShare, true))
    }

    const draw = () => {
      raf = requestAnimationFrame(draw)
      if (document.hidden) return
      frame += 1
      const m = MOODS[moodRef.current]
      ctx.clearRect(0, 0, width, height)

      // Junction dots on the grid, breathing slowly.
      const breathe = 0.05 + 0.03 * Math.sin(frame / 90)
      ctx.fillStyle = `rgba(139,152,165,${breathe})`
      for (let x = GRID; x < width; x += GRID) {
        for (let y = GRID; y < height; y += GRID) ctx.fillRect(x - 1, y - 1, 2, 2)
      }

      for (let i = 0; i < pulses.length; i += 1) {
        const p = pulses[i]
        p.pos += p.speed * m.speed
        const length = p.horizontal ? width : height
        if (p.pos - p.tail > length) {
          pulses[i] = spawn(width, height, m.failShare)
          continue
        }
        const passed = !p.startsFailing || p.pos > p.checkpoint
        if (p.startsFailing && p.pos > p.checkpoint && p.flash === 0 && moodRef.current !== 'error') p.flash = 1
        const failing = moodRef.current === 'error' ? true : !passed
        const rgb = moodRef.current === 'scanning' && !failing ? SCAN : failing ? FAIL : PASS

        const [hx, hy] = p.horizontal ? [p.pos, p.lane] : [p.lane, p.pos]
        const [tx, ty] = p.horizontal ? [p.pos - p.tail, p.lane] : [p.lane, p.pos - p.tail]
        const gradient = ctx.createLinearGradient(tx, ty, hx, hy)
        gradient.addColorStop(0, `rgba(${rgb},0)`)
        gradient.addColorStop(1, `rgba(${rgb},0.55)`)
        ctx.strokeStyle = gradient
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.moveTo(tx, ty)
        ctx.lineTo(hx, hy)
        ctx.stroke()

        ctx.fillStyle = `rgba(${rgb},0.9)`
        ctx.beginPath()
        ctx.arc(hx, hy, 1.8, 0, Math.PI * 2)
        ctx.fill()

        // The "greenlit" moment: a ring bursting out of the checkpoint.
        if (p.flash > 0) {
          const [cx, cy] = p.horizontal ? [p.checkpoint, p.lane] : [p.lane, p.checkpoint]
          ctx.strokeStyle = `rgba(${PASS},${p.flash * 0.7})`
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.arc(cx, cy, 3 + (1 - p.flash) * 18, 0, Math.PI * 2)
          ctx.stroke()
          p.flash = Math.max(0, p.flash - 0.025)
          if (p.flash === 0) p.flash = -1 // done, don't burst again
        }
      }
    }

    resize()
    window.addEventListener('resize', resize)
    draw()
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [reducedMotion])

  const m = MOODS[mood]
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* Aurora: two soft glows whose colour follows the run. */}
      <div
        className="absolute -top-1/3 left-1/2 h-[80vh] w-[90vw] -translate-x-1/2 rounded-full opacity-60 blur-3xl transition-[background] duration-[1500ms]"
        style={{ background: `radial-gradient(closest-side, rgba(${m.aurora},0.16), transparent)` }}
      />
      <div
        className="absolute -right-1/4 -bottom-1/3 h-[70vh] w-[60vw] rounded-full opacity-50 blur-3xl transition-[background] duration-[1500ms]"
        style={{ background: `radial-gradient(closest-side, rgba(${m.aurora2},0.10), transparent)` }}
      />
      {/* Grid lines, faded out towards the edges. */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'linear-gradient(to right, rgba(139,152,165,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(139,152,165,0.05) 1px, transparent 1px)',
          backgroundSize: `${GRID}px ${GRID}px`,
          maskImage: 'radial-gradient(ellipse at 50% 40%, #000 30%, transparent 85%)',
          WebkitMaskImage: 'radial-gradient(ellipse at 50% 40%, #000 30%, transparent 85%)',
        }}
      />
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
      {/* A slow scan line, like a monitor refreshing. */}
      {!reducedMotion && (
        <div
          className="absolute inset-x-0 top-0 h-24"
          style={{
            background: `linear-gradient(to bottom, transparent, rgba(${m.aurora},0.035), transparent)`,
            animation: 'scanline 9s linear infinite',
          }}
        />
      )}
    </div>
  )
}
