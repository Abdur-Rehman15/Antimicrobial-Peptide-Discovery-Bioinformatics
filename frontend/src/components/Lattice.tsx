import { useEffect, useRef } from 'react'

const COUNT = 54
const LINK = 150 // px: draw a line between two points closer than this
const SPEED = 0.1 // px per frame

/**
 * A molecular lattice drifting behind everything: points joined by faint lines when they come
 * close, the way a contact map or a coarse molecular model is drawn. It sits at a few percent
 * opacity and never takes the pointer. If you notice it, it is too strong.
 *
 * Canvas rather than SVG because the whole field redraws every frame. Honours reduced motion by
 * painting one static frame and stopping.
 */
export function Lattice() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return

    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    const dots = Array.from({ length: COUNT }, () => ({
      x: Math.random(),
      y: Math.random(),
      dx: (Math.random() - 0.5) * SPEED,
      dy: (Math.random() - 0.5) * SPEED,
    }))
    let width = 0
    let height = 0
    let frame = 0

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = canvas.clientWidth
      height = canvas.clientHeight
      canvas.width = Math.max(1, Math.round(width * ratio))
      canvas.height = Math.max(1, Math.round(height * ratio))
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
    }

    const draw = () => {
      context.clearRect(0, 0, width, height)
      const points = dots.map((d) => ({ x: d.x * width, y: d.y * height }))
      context.strokeStyle = '#8A9BA8'
      context.fillStyle = '#8A9BA8'
      context.lineWidth = 1
      for (let i = 0; i < points.length; i++) {
        for (let j = i + 1; j < points.length; j++) {
          const gap = Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y)
          if (gap > LINK) continue
          context.globalAlpha = (1 - gap / LINK) * 0.03
          context.beginPath()
          context.moveTo(points[i].x, points[i].y)
          context.lineTo(points[j].x, points[j].y)
          context.stroke()
        }
      }
      context.globalAlpha = 0.05
      for (const p of points) {
        context.beginPath()
        context.arc(p.x, p.y, 1.4, 0, Math.PI * 2)
        context.fill()
      }
    }

    const step = () => {
      for (const d of dots) {
        d.x += d.dx / Math.max(width, 1)
        d.y += d.dy / Math.max(height, 1)
        if (d.x < 0 || d.x > 1) d.dx *= -1
        if (d.y < 0 || d.y > 1) d.dy *= -1
      }
      draw()
      frame = requestAnimationFrame(step)
    }

    resize()
    draw()
    if (!still) frame = requestAnimationFrame(step)
    const onResize = () => {
      resize()
      draw()
    }
    window.addEventListener('resize', onResize)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', onResize)
    }
  }, [])

  return <canvas className="lattice" ref={ref} aria-hidden />
}
