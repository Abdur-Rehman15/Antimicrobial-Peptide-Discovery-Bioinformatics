import type { View } from '../api/types'
import {
  DEFAULT_VIEW,
  changedCount,
  parseView,
  prevalenceToSlider,
  serializeView,
  sliderToPrevalence,
  viewToApi,
  viewsEqual,
} from './view'

const custom: View = {
  activityWeight: 2,
  safetyWeight: 0.5,
  noveltyWeight: 0,
  prevalence: 1e-4,
  hideKnown: true,
  novelty: ['novel', 'related'],
  maxHemolysis: 0.33,
  minLength: 10,
  maxLength: 30,
  accession: 'P02788',
}

describe('view <-> URL', () => {
  it('leaves everything out when the view is the default', () => {
    expect(serializeView(DEFAULT_VIEW).toString()).toBe('')
    expect(changedCount(DEFAULT_VIEW)).toBe(0)
    expect(parseView(new URLSearchParams(''))).toEqual(DEFAULT_VIEW)
  })

  it('round-trips a changed view', () => {
    expect(parseView(serializeView(custom))).toEqual(custom)
    expect(changedCount(custom)).toBe(10)
  })

  it('ignores garbage and clamps out-of-range numbers', () => {
    const view = parseView(
      new URLSearchParams('aw=abc&sw=99&nw=-4&p=5&mh=2&nv=novel,bogus,novel&lo=0&hi=9999&hk=yes'),
    )
    expect(view.activityWeight).toBe(1) // not a number: default
    expect(view.safetyWeight).toBe(3) // clamped to the maximum weight
    expect(view.noveltyWeight).toBe(0)
    expect(view.prevalence).toBe(0.1) // clamped
    expect(view.maxHemolysis).toBe(1)
    expect(view.novelty).toEqual(['novel']) // bogus class dropped, duplicates removed
    expect(view.minLength).toBe(1)
    expect(view.maxLength).toBe(500)
    expect(view.hideKnown).toBe(false) // only "1" counts
  })

  it('writes the backend query parameters', () => {
    const api = viewToApi(custom)
    expect(api.get('activity_weight')).toBe('2')
    expect(api.get('safety_weight')).toBe('0.5')
    expect(api.get('novelty_weight')).toBe('0')
    expect(api.get('prevalence')).toBe('0.0001')
    expect(api.get('hide_known')).toBe('true')
    expect(api.get('novelty')).toBe('novel,related')
    expect(api.get('max_hemolysis')).toBe('0.33')
    expect(api.get('min_length')).toBe('10')
    expect(api.get('max_length')).toBe('30')
    expect(api.get('accession')).toBe('P02788')
    // the default view still sends the three weights and the rarity, and nothing else
    expect([...viewToApi(DEFAULT_VIEW).keys()].sort()).toEqual([
      'activity_weight',
      'novelty_weight',
      'prevalence',
      'safety_weight',
    ])
  })

  it('compares views by what they say', () => {
    expect(viewsEqual(DEFAULT_VIEW, { ...DEFAULT_VIEW })).toBe(true)
    expect(viewsEqual(DEFAULT_VIEW, { ...DEFAULT_VIEW, hideKnown: true })).toBe(false)
  })

  it('maps the logarithmic rarity slider both ways without float noise', () => {
    expect(prevalenceToSlider(0.001)).toBeCloseTo(-3, 10)
    expect(sliderToPrevalence(-3)).toBe(0.001)
    expect(sliderToPrevalence(-4.5)).toBe(0.000032)
    for (const s of [-5, -4.25, -3, -2, -1]) {
      expect(prevalenceToSlider(sliderToPrevalence(s))).toBeCloseTo(s, 1)
    }
  })
})
