import { ArrowDown, ArrowUp } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

import { cn } from '../../lib/cn'

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  /** Value used for sorting; omit to make the column unsortable. */
  sortValue?: (row: T) => string | number | null | undefined
  align?: 'left' | 'right'
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  initialSort?: { key: string; dir: 'asc' | 'desc' }
  onRowClick?: (row: T) => void
  selectedKey?: string | number | null
  empty?: ReactNode
  caption?: string
  testId?: string
}

/** Sortable table. Sorting is client-side; server paging arrives with larger datasets. */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  initialSort,
  onRowClick,
  selectedKey,
  empty = 'No rows.',
  caption,
  testId,
}: Props<T>) {
  const [sort, setSort] = useState(initialSort)
  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort?.key)
    if (!col?.sortValue || !sort) return rows
    const get = col.sortValue
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const va = get(a)
      const vb = get(b)
      if (va === vb) return 0
      if (va === null || va === undefined) return 1
      if (vb === null || vb === undefined) return -1
      return va < vb ? -dir : dir
    })
  }, [rows, columns, sort])

  if (rows.length === 0) return <p className="py-4 text-sm text-muted">{empty}</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm" data-testid={testId}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="text-muted">
          <tr>
            {columns.map((c) => {
              const active = sort?.key === c.key
              const ariaSort = active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'
              return (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={c.sortValue ? ariaSort : undefined}
                  className={cn('py-1.5 pr-3 font-medium', c.align === 'right' && 'text-right')}
                >
                  {c.sortValue ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-text"
                      onClick={() =>
                        setSort({ key: c.key, dir: active && sort.dir === 'asc' ? 'desc' : 'asc' })
                      }
                    >
                      {c.header}
                      {active &&
                        (sort.dir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const key = rowKey(row)
            return (
              <tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                aria-selected={selectedKey === key ? true : undefined}
                className={cn(
                  'border-t border-border align-top',
                  onRowClick && 'cursor-pointer hover:bg-surface-2',
                  selectedKey === key && 'bg-surface-2',
                )}
              >
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={cn('py-1.5 pr-3', c.align === 'right' && 'text-right tabular-nums')}
                  >
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
