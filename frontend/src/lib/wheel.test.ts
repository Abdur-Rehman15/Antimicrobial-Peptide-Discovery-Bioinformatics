import { momentDirection, residueClass, wheelPositions } from './wheel'

describe('helical wheel geometry', () => {
  it('puts residue 1 at the top and turns 100 degrees per residue', () => {
    const p = wheelPositions('ACDEF', 10)
    expect(p.map((r) => r.angle)).toEqual([0, 100, 200, 300, 40])
    expect(p[0].x).toBeCloseTo(0)
    expect(p[0].y).toBeCloseTo(-10) // straight up on screen
    expect(p[1].x).toBeCloseTo(10 * Math.sin((100 * Math.PI) / 180))
    expect(p[1].y).toBeCloseTo(-10 * Math.cos((100 * Math.PI) / 180))
    for (const r of p) expect(Math.hypot(r.x, r.y)).toBeCloseTo(10)
  })

  it('classifies residues', () => {
    expect(residueClass('K')).toBe('positive')
    expect(residueClass('R')).toBe('positive')
    expect(residueClass('D')).toBe('negative')
    expect(residueClass('E')).toBe('negative')
    expect(residueClass('L')).toBe('hydrophobic')
    expect(residueClass('W')).toBe('hydrophobic')
    expect(residueClass('S')).toBe('polar')
    expect(residueClass('G')).toBe('polar')
  })

  it('points the moment at a single oily residue', () => {
    const m = momentDirection('L')!
    expect(m.angle).toBeCloseTo(0)
    expect(m.magnitude).toBeCloseTo(1.06)
  })

  it('points away from a single charged residue and is null for nothing', () => {
    // K has a negative Eisenberg value, so the oily side is opposite to it
    expect(momentDirection('K')!.angle).toBeCloseTo(180)
    expect(momentDirection('')).toBeNull()
    expect(momentDirection('XXXX')).toBeNull() // no residue with a known value
  })

  it('points into the middle of a group of oily residues', () => {
    // three L at 0, 100 and 200 degrees: the middle of the group is 100 degrees
    const m = momentDirection('LLL')!
    expect(m.angle).toBeGreaterThan(95)
    expect(m.angle).toBeLessThan(105)
  })

  it('is pushed away from charged residues too', () => {
    // by hand: L at 0, 100, 200 and K at 300, 40, 140 degrees sum to x=0.052, y=-0.871,
    // i.e. about 177 degrees: between the oily group (100) and the side opposite the lysines
    const m = momentDirection('LLLKKK')!
    expect(m.angle).toBeCloseTo(176.6, 0)
  })
})
