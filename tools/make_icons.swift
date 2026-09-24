// SPDX-License-Identifier: GPL-3.0-or-later
// Draws the S-Log MetaRaw icons (installer, disk image, SLogMetaRaw OpenFX effect).
// Usage: swift tools/make_icons.swift <output dir>
// Writes icon_1024.png (app/installer icon), effect_256.png and detail_256.png (OpenFX node icons).
import AppKit

func color(_ hex: UInt32, _ alpha: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255, alpha: alpha)
}

// warm (3200K) -> neutral -> cool (7500K), the white-balance idea of the plugin
let bladeColors: [NSColor] = [color(0xFF8A3D), color(0xFFB347), color(0xFFE08A),
                              color(0xBFE3FF), color(0x6FB6FF), color(0x3D7BFF)]

// Aperture (lens ring, blades, opening) alone on a transparent layer.
func drawAperture(size: CGFloat) -> NSBitmapImageRep {
    return drawIconLayer(size: size, withBackground: false, apertureOnly: true)
}

func drawIconLayer(size: CGFloat, withBackground: Bool, apertureOnly: Bool) -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let ctx = NSGraphicsContext.current!.cgContext
    ctx.setShouldAntialias(true)
    let s = size
    let c = CGPoint(x: s / 2, y: s / 2)

    if withBackground && !apertureOnly {
        // macOS-style rounded square with a graphite gradient
        let inset = s * 0.09
        let rect = CGRect(x: inset, y: inset, width: s - 2 * inset, height: s - 2 * inset)
        let bg = NSBezierPath(roundedRect: rect, xRadius: rect.width * 0.225, yRadius: rect.width * 0.225)
        NSGraphicsContext.saveGraphicsState()
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.35)
        shadow.shadowBlurRadius = s * 0.025
        shadow.shadowOffset = NSSize(width: 0, height: -s * 0.012)
        shadow.set()
        color(0x1B1E24).setFill()
        bg.fill()
        NSGraphicsContext.restoreGraphicsState()
        NSGradient(starting: color(0x2E333D), ending: color(0x121418))!.draw(in: bg, angle: -90)
        // subtle top highlight
        color(0xFFFFFF, 0.06).setStroke()
        bg.lineWidth = s * 0.006
        bg.stroke()
    }
    if !apertureOnly {  // background tile only
        ctx.flush()
        NSGraphicsContext.restoreGraphicsState()
        return rep
    }

    let outer = s * 0.30
    let inner = outer * 0.34
    let blades = 6
    let twist = CGFloat.pi / 3.2

    // lens ring
    let ring = NSBezierPath(ovalIn: CGRect(x: c.x - outer * 1.10, y: c.y - outer * 1.10, width: outer * 2.2, height: outer * 2.2))
    NSGradient(starting: color(0x4A505C), ending: color(0x16181C))!.draw(in: ring, angle: -90)
    let ringInner = NSBezierPath(ovalIn: CGRect(x: c.x - outer * 1.02, y: c.y - outer * 1.02, width: outer * 2.04, height: outer * 2.04))
    color(0x0B0C0E).setFill()
    ringInner.fill()

    // aperture blades, clipped to the lens
    NSGraphicsContext.saveGraphicsState()
    NSBezierPath(ovalIn: CGRect(x: c.x - outer, y: c.y - outer, width: outer * 2, height: outer * 2)).addClip()
    for i in 0..<blades {
        let a0 = CGFloat(i) * 2 * .pi / CGFloat(blades) + .pi / 2
        let a1 = a0 + 2 * .pi / CGFloat(blades)
        let p = NSBezierPath()
        p.move(to: CGPoint(x: c.x + inner * cos(a0), y: c.y + inner * sin(a0)))
        p.line(to: CGPoint(x: c.x + inner * cos(a1), y: c.y + inner * sin(a1)))
        p.line(to: CGPoint(x: c.x + outer * 1.6 * cos(a1 + twist), y: c.y + outer * 1.6 * sin(a1 + twist)))
        p.line(to: CGPoint(x: c.x + outer * 1.6 * cos(a0 + twist), y: c.y + outer * 1.6 * sin(a0 + twist)))
        p.close()
        let base = bladeColors[i]
        NSGradient(starting: base.highlight(withLevel: 0.25) ?? base, ending: base.shadow(withLevel: 0.25) ?? base)!
            .draw(in: p, angle: (a0 + a1) / 2 * 180 / .pi)
        color(0x0B0C0E, 0.9).setStroke()
        p.lineWidth = s * 0.008
        p.stroke()
    }
    NSGraphicsContext.restoreGraphicsState()

    // opening: dark glass with a small reflection
    let hole = NSBezierPath()
    for i in 0...blades {
        let a = CGFloat(i) * 2 * .pi / CGFloat(blades) + .pi / 2
        let pt = CGPoint(x: c.x + inner * cos(a), y: c.y + inner * sin(a))
        if i == 0 { hole.move(to: pt) } else { hole.line(to: pt) }
    }
    hole.close()
    NSGradient(starting: color(0x1C2230), ending: color(0x05060A))!.draw(in: hole, angle: -60)
    let glint = NSBezierPath(ovalIn: CGRect(x: c.x - inner * 0.55, y: c.y + inner * 0.05, width: inner * 0.5, height: inner * 0.32))
    color(0xFFFFFF, 0.28).setFill()
    glint.fill()

    ctx.flush()
    NSGraphicsContext.restoreGraphicsState()
    return rep
}

// Final icon: graphite tile, left half = optical aperture, right half = the same
// aperture sampled into square pixels that thin out towards the edge (captured light
// becoming data), split by a thin scan line.
func drawIcon(size s: CGFloat) -> NSBitmapImageRep {
    let tile = drawIconLayer(size: s, withBackground: true, apertureOnly: false)   // background only below
    let ap = drawAperture(size: s)
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(s), pixelsHigh: Int(s),
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                               colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let rect = NSRect(x: 0, y: 0, width: s, height: s)
    tile.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: false, hints: nil)
    let cx = s / 2

    // analog half
    NSGraphicsContext.saveGraphicsState()
    NSBezierPath(rect: NSRect(x: 0, y: 0, width: cx, height: s)).addClip()
    ap.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: false, hints: nil)
    NSGraphicsContext.restoreGraphicsState()

    // digital half: sample the aperture on a grid
    let cell = s / 30
    let gap = cell * 0.18
    let outer = s * 0.30 * 1.10
    var y = s / 2 - outer
    while y < s / 2 + outer {
        var x = cx
        while x < cx + outer * 1.45 {
            let px = Int(x + cell / 2), py = Int(y + cell / 2)
            if px >= 0 && px < Int(s) && py >= 0 && py < Int(s),
               let col = ap.colorAt(x: px, y: Int(s) - 1 - py), col.alphaComponent > 0.5,
               (col.usingColorSpace(.sRGB)?.brightnessComponent ?? 0) > 0.35 {
                let t = (x - cx) / (outer * 1.45)                  // 0 at the seam -> 1 far right
                let dx = x + cell / 2 - s / 2, dy = y + cell / 2 - s / 2
                let r = sqrt(dx * dx + dy * dy)
                // keep every cell inside the lens; outside, scatter a few cells (hash) that fade out
                var keep = r <= outer * 0.98
                var alpha: CGFloat = 1
                var scale: CGFloat = 1
                if !keep {
                    let h = (Int(x / cell) * 73856093 ^ Int(y / cell) * 19349663) & 1023
                    keep = CGFloat(h) / 1023 > 0.55 + 0.4 * t
                    alpha = max(0, 0.85 - t)
                    scale = 0.7
                } else {
                    scale = 1 - 0.35 * t
                }
                if keep {
                    let sz = (cell - gap) * scale
                    let sq = NSBezierPath(roundedRect: NSRect(x: x + (cell - sz) / 2, y: y + (cell - sz) / 2, width: sz, height: sz),
                                          xRadius: sz * 0.18, yRadius: sz * 0.18)
                    col.withAlphaComponent(alpha).setFill()
                    sq.fill()
                }
            }
            x += cell
        }
        y += cell
    }
    // scattered data points drifting out of the lens on the right
    var seed: UInt32 = 12345
    for _ in 0..<26 {
        seed = seed &* 1103515245 &+ 12345
        let fx = CGFloat(seed % 1000) / 1000
        seed = seed &* 1103515245 &+ 12345
        let fy = CGFloat(seed % 1000) / 1000
        let x = cx + outer * 1.0 + (s * 0.86 - cx - outer * 1.0) * fx
        let y = s / 2 - outer * 0.9 + fy * outer * 1.8
        let sz = cell * (0.55 - 0.35 * fx)
        bladeColors[Int(seed) % bladeColors.count].withAlphaComponent(0.75 - 0.6 * fx).setFill()
        NSBezierPath(roundedRect: NSRect(x: x, y: y, width: sz, height: sz), xRadius: sz * 0.2, yRadius: sz * 0.2).fill()
    }

    // scan line at the seam
    let lineH = outer * 2.25
    let line = NSRect(x: cx - s * 0.003, y: s / 2 - lineH / 2, width: s * 0.006, height: lineH)
    NSGradient(colors: [color(0xFFFFFF, 0), color(0xFFFFFF, 0.85), color(0xFFFFFF, 0)])!.draw(in: line, angle: 90)
    NSGraphicsContext.restoreGraphicsState()
    return rep
}

// The Detail node: the same tile with a badge of stacked ripples (local contrast, texture).
func drawDetailIcon(size s: CGFloat) -> NSBitmapImageRep {
    let base = drawIcon(size: s)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: base)
    let r = s * 0.2, c = CGPoint(x: s * 0.76, y: s * 0.24)
    let badge = NSBezierPath(ovalIn: CGRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r))
    color(0x15171C).setFill()
    badge.fill()
    color(0xFFFFFF, 0.85).setStroke()
    badge.lineWidth = s * 0.012
    badge.stroke()
    for (i, a) in [0.45, 0.75, 1.0].enumerated() {
        let y0 = c.y - r * 0.45 + CGFloat(i) * r * 0.45
        let wave = NSBezierPath()
        wave.lineWidth = s * 0.016
        wave.lineCapStyle = .round
        var x = c.x - r * 0.62
        wave.move(to: CGPoint(x: x, y: y0))
        while x <= c.x + r * 0.62 {
            let phase = (x - (c.x - r * 0.62)) / (r * 1.24) * 2 * .pi * 2
            wave.line(to: CGPoint(x: x, y: y0 + sin(phase) * r * 0.12 * CGFloat(a)))
            x += s * 0.004
        }
        color(0xFFB347, CGFloat(a)).setStroke()
        wave.stroke()
    }
    NSGraphicsContext.restoreGraphicsState()
    return base
}

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "."
try! drawIcon(size: 1024).representation(using: .png, properties: [:])!
    .write(to: URL(fileURLWithPath: out + "/icon_1024.png"))
try! drawIcon(size: 256).representation(using: .png, properties: [:])!
    .write(to: URL(fileURLWithPath: out + "/effect_256.png"))
try! drawDetailIcon(size: 256).representation(using: .png, properties: [:])!
    .write(to: URL(fileURLWithPath: out + "/detail_256.png"))
print("icons written to \(out)")
