// The "view" is how the saved shortlist is ranked and filtered. It lives in the page URL, so a
// link to a run reproduces exactly what the sender saw.

import type { NoveltyClass, View } from '../api/types'

export const DEFAULT_PREVALENCE = 1e-3
export const MAX_WEIGHT = 3
export const MIN_PREVALENCE = 1e-5
export const MAX_PREVALENCE = 1e-1

export const DEFAULT_VIEW: View = {
  activityWeight: 1,
  safetyWeight: 1,
  noveltyWeight: 1,
  prevalence: DEFAULT_PREVALENCE,
  hideKnown: false,
  novelty: [],
  maxHemolysis: null,
  minLength: null,
  maxLength: null,
  accession: null,
}

const CLASSES: NoveltyClass[] = ['known', 'related', 'novel']

function number(text: string | null, lo: number, hi: number): number | null {
  if (text === null || text.trim() === '') return null
  const value = Number(text)
  if (!Number.isFinite(value)) return null
  return Math.min(hi, Math.max(lo, value))
}

/** Read a view from URL parameters. Anything missing or invalid falls back to the default. */
export function parseView(params: URLSearchParams): View {
  const classes = (params.get('nv') ?? '')
    .split(',')
    .filter((c): c is NoveltyClass => (CLASSES as string[]).includes(c))
  return {
    activityWeight: number(params.get('aw'), 0, MAX_WEIGHT) ?? DEFAULT_VIEW.activityWeight,
    safetyWeight: number(params.get('sw'), 0, MAX_WEIGHT) ?? DEFAULT_VIEW.safetyWeight,
    noveltyWeight: number(params.get('nw'), 0, MAX_WEIGHT) ?? DEFAULT_VIEW.noveltyWeight,
    prevalence: number(params.get('p'), MIN_PREVALENCE, MAX_PREVALENCE) ?? DEFAULT_PREVALENCE,
    hideKnown: params.get('hk') === '1',
    novelty: [...new Set(classes)],
    maxHemolysis: number(params.get('mh'), 0, 1),
    minLength: number(params.get('lo'), 1, 500),
    maxLength: number(params.get('hi'), 1, 500),
    accession: params.get('acc') || null,
  }
}

/** Write a view as URL parameters, leaving out everything that is still the default. */
export function serializeView(view: View): URLSearchParams {
  const out = new URLSearchParams()
  if (view.activityWeight !== DEFAULT_VIEW.activityWeight) out.set('aw', String(view.activityWeight))
  if (view.safetyWeight !== DEFAULT_VIEW.safetyWeight) out.set('sw', String(view.safetyWeight))
  if (view.noveltyWeight !== DEFAULT_VIEW.noveltyWeight) out.set('nw', String(view.noveltyWeight))
  if (view.prevalence !== DEFAULT_PREVALENCE) out.set('p', String(view.prevalence))
  if (view.hideKnown) out.set('hk', '1')
  if (view.novelty.length > 0) out.set('nv', view.novelty.join(','))
  if (view.maxHemolysis !== null) out.set('mh', String(view.maxHemolysis))
  if (view.minLength !== null) out.set('lo', String(view.minLength))
  if (view.maxLength !== null) out.set('hi', String(view.maxLength))
  if (view.accession) out.set('acc', view.accession)
  return out
}

/** The same view as the backend's query parameters (docs/API.md). */
export function viewToApi(view: View): URLSearchParams {
  const out = new URLSearchParams()
  out.set('activity_weight', String(view.activityWeight))
  out.set('safety_weight', String(view.safetyWeight))
  out.set('novelty_weight', String(view.noveltyWeight))
  out.set('prevalence', String(view.prevalence))
  if (view.hideKnown) out.set('hide_known', 'true')
  if (view.novelty.length > 0) out.set('novelty', view.novelty.join(','))
  if (view.maxHemolysis !== null) out.set('max_hemolysis', String(view.maxHemolysis))
  if (view.minLength !== null) out.set('min_length', String(view.minLength))
  if (view.maxLength !== null) out.set('max_length', String(view.maxLength))
  if (view.accession) out.set('accession', view.accession)
  return out
}

export function viewsEqual(a: View, b: View): boolean {
  return serializeView(a).toString() === serializeView(b).toString()
}

/** Number of things that differ from the default view (shown on the "Reset" button). */
export function changedCount(view: View): number {
  return [...serializeView(view).keys()].length
}

// The prevalence slider is logarithmic: position -5 ... -1 is 10^position.
export const prevalenceToSlider = (p: number): number => Math.log10(p)
export const sliderToPrevalence = (s: number): number =>
  Number((10 ** s).toPrecision(2)) // 0.0010000000000000002 -> 0.001
