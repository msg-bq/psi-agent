export const METHOD_COMMAND_PREFIX = '/method:'

const METHOD_NAME_RE = /^[a-z][a-z0-9-]{0,63}$/
const WINDOWS_RESERVED_METHOD_NAMES = new Set([
  'con',
  'prn',
  'aux',
  'nul',
  ...Array.from({ length: 9 }, (_, index) => `com${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `lpt${index + 1}`),
])

function isValidMethodName(name) {
  return typeof name === 'string'
    && METHOD_NAME_RE.test(name)
    && !WINDOWS_RESERVED_METHOD_NAMES.has(name)
}

function invalid(error) {
  return { kind: 'invalid', error }
}

export function parseMethodCommand(value) {
  const text = String(value ?? '').trim()
  if (!text.startsWith(METHOD_COMMAND_PREFIX)) return { kind: 'text' }

  const name = text.slice(METHOD_COMMAND_PREFIX.length)
  if (!name) return invalid('请输入要运行的方法名称，例如 /method:daily-brief')
  if (/\s/.test(name)) {
    return invalid('方法指令只支持 /method:<名称>，不能附加参数')
  }
  if (!isValidMethodName(name)) {
    return invalid('方法名称必须以小写字母开头，只能包含小写字母、数字和连字符，且不能使用系统保留名')
  }
  return { kind: 'method', name }
}

export function getMethodCommandQuery(value) {
  const text = String(value ?? '').trimStart()
  if (!text || /\s/.test(text)) return null

  if (METHOD_COMMAND_PREFIX.startsWith(text)) return ''
  if (!text.startsWith(METHOD_COMMAND_PREFIX)) return null
  return text.slice(METHOD_COMMAND_PREFIX.length)
}

export function filterMethodOptions(methods, query = '') {
  if (!Array.isArray(methods)) return []
  const needle = String(query).toLowerCase()

  return methods
    .filter(method => method
      && isValidMethodName(method.name))
    .map((method, index) => {
      const name = method.name.toLowerCase()
      let rank = 3
      if (!needle) rank = 0
      else if (name === needle) rank = 0
      else if (name.startsWith(needle)) rank = 1
      else if (name.includes(needle)) rank = 2
      return { method, index, rank }
    })
    .filter(item => item.rank < 3)
    .sort((a, b) => a.rank - b.rank
      || a.method.name.localeCompare(b.method.name)
      || a.index - b.index)
    .map(item => item.method)
}

export function formatMethodCommand(method) {
  const name = method?.name
  if (!isValidMethodName(name)) {
    throw new Error('Invalid method name')
  }
  return `${METHOD_COMMAND_PREFIX}${name}`
}

export function moveMethodSelection(current, count, delta) {
  if (!Number.isInteger(count) || count <= 0) return -1
  if (!Number.isInteger(current) || current < 0 || current >= count) {
    return delta < 0 ? count - 1 : 0
  }
  return (current + delta + count) % count
}
