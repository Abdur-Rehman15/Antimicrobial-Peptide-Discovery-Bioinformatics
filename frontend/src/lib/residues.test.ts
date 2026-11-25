import { chargeSummary, textClass } from './residues'

describe('how a residue is drawn', () => {
  it('splits residues by charge at pH 7.4', () => {
    expect(textClass('K')).toBe('basic')
    expect(textClass('R')).toBe('basic')
    expect(textClass('D')).toBe('acidic')
    expect(textClass('E')).toBe('acidic')
    expect(textClass('H')).toBe('weak-basic') // only partly protonated
  })

  it('marks the oily residues and leaves the rest plain', () => {
    for (const aa of 'ACFILMVW') expect(textClass(aa)).toBe('oily')
    for (const aa of 'GNPQSTY') expect(textClass(aa)).toBe('other')
  })

  it('gives every one of the twenty residues exactly one class', () => {
    const seen = [...'ACDEFGHIKLMNPQRSTVWY'].map(textClass)
    expect(seen).toHaveLength(20)
    expect(seen.every(Boolean)).toBe(true)
    // charged and oily are disjoint, so a letter never needs both a colour and a shade
    const charged = [...'KRDEH']
    expect(charged.some((aa) => textClass(aa) === 'oily')).toBe(false)
  })

  it('counts the classes of a peptide', () => {
    // magainin 2: 4 basic (K K K K), 2 acidic (E, plus none), oily A C F I L M V W
    expect(chargeSummary('KRDEAL')).toEqual({ basic: 2, acidic: 2, oily: 2 })
    expect(chargeSummary('')).toEqual({ basic: 0, acidic: 0, oily: 0 })
    expect(chargeSummary('GGGG')).toEqual({ basic: 0, acidic: 0, oily: 0 })
  })
})
