import { describe, expect, it } from 'vitest'
import {
  filterMethodOptions,
  formatMethodCommand,
  getMethodCommandQuery,
  moveMethodSelection,
  parseMethodCommand,
} from './methodCommands.js'

describe('parseMethodCommand', () => {
  it('leaves ordinary messages untouched', () => {
    expect(parseMethodCommand('hello')).toEqual({ kind: 'text' })
    expect(parseMethodCommand('please use /method:daily-brief')).toEqual({ kind: 'text' })
    expect(parseMethodCommand('/methods:daily-brief')).toEqual({ kind: 'text' })
  })

  it('parses the exact method command', () => {
    expect(parseMethodCommand('/method:daily-brief')).toEqual({
      kind: 'method',
      name: 'daily-brief',
    })
    expect(parseMethodCommand('  /method:daily-brief  ')).toEqual({
      kind: 'method',
      name: 'daily-brief',
    })
  })

  it('rejects missing and invalid method names', () => {
    expect(parseMethodCommand('/method:').kind).toBe('invalid')
    expect(parseMethodCommand('/method:Daily').kind).toBe('invalid')
    expect(parseMethodCommand('/method:daily_brief').kind).toBe('invalid')
    expect(parseMethodCommand('/method:1daily').kind).toBe('invalid')
    expect(parseMethodCommand('/method:con').kind).toBe('invalid')
    expect(parseMethodCommand('/method:com9').kind).toBe('invalid')
    expect(parseMethodCommand('/method:lpt1').kind).toBe('invalid')
    expect(parseMethodCommand(`/method:a${'b'.repeat(64)}`).kind).toBe('invalid')
    expect(parseMethodCommand(`/method:a${'b'.repeat(63)}`).kind).toBe('method')
  })

  it('rejects every command suffix', () => {
    expect(parseMethodCommand('/method:daily anything').kind).toBe('invalid')
    expect(parseMethodCommand('/method:daily []').kind).toBe('invalid')
    expect(parseMethodCommand('/method:daily {}').kind).toBe('invalid')
  })
})

describe('getMethodCommandQuery', () => {
  it('returns the active partial command query', () => {
    expect(getMethodCommandQuery('/')).toBe('')
    expect(getMethodCommandQuery('/meth')).toBe('')
    expect(getMethodCommandQuery('/method:')).toBe('')
    expect(getMethodCommandQuery('/method:daily')).toBe('daily')
  })

  it('closes autocomplete for ordinary text or any suffix', () => {
    expect(getMethodCommandQuery('hello')).toBeNull()
    expect(getMethodCommandQuery('/method:daily ')).toBeNull()
    expect(getMethodCommandQuery('/method:daily anything')).toBeNull()
  })
})

describe('filterMethodOptions', () => {
  const methods = [
    { name: 'weekly-review' },
    { name: 'daily-brief' },
    { name: 'research' },
    { name: 'Invalid_Name' },
    null,
  ]

  it('filters malformed records and sorts all methods by name', () => {
    expect(filterMethodOptions(methods, '').map(item => item.name)).toEqual([
      'daily-brief',
      'research',
      'weekly-review',
    ])
  })

  it('ranks exact and prefix name matches', () => {
    expect(filterMethodOptions(methods, 'research').map(item => item.name)).toEqual([
      'research',
    ])
  })
})

describe('formatMethodCommand', () => {
  it('formats only the exact command', () => {
    expect(formatMethodCommand({ name: 'daily-brief' })).toBe('/method:daily-brief')
    expect(() => formatMethodCommand({ name: '../escape' })).toThrow()
  })
})

describe('moveMethodSelection', () => {
  it('wraps in both directions and handles an unset selection', () => {
    expect(moveMethodSelection(-1, 3, 1)).toBe(0)
    expect(moveMethodSelection(-1, 3, -1)).toBe(2)
    expect(moveMethodSelection(2, 3, 1)).toBe(0)
    expect(moveMethodSelection(0, 3, -1)).toBe(2)
    expect(moveMethodSelection(0, 0, 1)).toBe(-1)
  })
})
