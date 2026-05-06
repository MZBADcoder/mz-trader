export function formatCompactNumber(value: number | null | undefined, locale: string) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-'
  }
  return new Intl.NumberFormat(locale, {
    notation: 'compact',
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatCurrency(value: number | null | undefined, locale: string) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-'
  }
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatPercent(value: number | null | undefined, locale: string) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-'
  }
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    maximumFractionDigits: 2,
  }).format(value / 100)
}

type FormatDateTimeOptions = {
  timeZone?: string
}

export function formatDateTime(
  value: string | null | undefined,
  locale: string,
  options: FormatDateTimeOptions = {},
) {
  if (!value) {
    return '-'
  }
  const formatOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: options.timeZone ?? 'UTC',
  }

  try {
    return new Intl.DateTimeFormat(locale, formatOptions).format(new Date(value))
  } catch {
    return new Intl.DateTimeFormat(locale, { ...formatOptions, timeZone: 'UTC' }).format(new Date(value))
  }
}

export function classNames(...values: Array<false | null | string | undefined>) {
  return values.filter(Boolean).join(' ')
}
