import { abbreviate, count, duration, estimatedSeconds, percent, probability, rarity } from './format'

describe('format', () => {
  it('formats counts and percentages', () => {
    expect(count(106812)).toBe('106,812')
    expect(count(null)).toBe('-')
    expect(percent(0.4375)).toBe('44%')
    expect(percent(0.4375, 1)).toBe('43.8%')
  })

  it('shows probabilities with a sensible number of digits', () => {
    expect(probability(0.4384)).toBe('0.44')
    expect(probability(0.0243)).toBe('0.024')
    expect(probability(0.0004)).toBe('<0.001')
    expect(probability(0.1)).toBe('0.10')
  })

  it('writes rarity as "1 in N"', () => {
    expect(rarity(0.001)).toBe('1 in 1,000')
    expect(rarity(1e-4)).toBe('1 in 10,000')
    expect(rarity(0.01)).toBe('1 in 100')
  })

  it('formats durations', () => {
    expect(duration(7.94)).toBe('7.9 s')
    expect(duration(45.2)).toBe('45 s')
    expect(duration(60)).toBe('1 min')
    expect(duration(200)).toBe('3 min 20 s')
    expect(duration(3725)).toBe('1 h 2 min')
    expect(duration(null)).toBe('-')
  })

  it('estimates the scan time from the proteins to scan', () => {
    // 100 proteins of 360 residues: 100 * 43 * 332 windows at 23,000 per second
    expect(estimatedSeconds(100)).toBeCloseTo((100 * 43 * 332) / 23000, 5)
    expect(estimatedSeconds(0)).toBe(0)
    expect(estimatedSeconds(10, 20)).toBe(0) // shorter than a window: nothing to scan
  })

  it('shortens long peptides but never short ones', () => {
    expect(abbreviate('KRWWK')).toBe('KRWWK')
    const long = 'A'.repeat(20) + 'L'.repeat(22)
    const short = abbreviate(long, 26)
    expect(short.length).toBeLessThanOrEqual(26)
    expect(short).toContain('…')
    expect(short.startsWith('AAAA')).toBe(true)
    expect(short.endsWith('LLLL')).toBe(true)
  })
})
