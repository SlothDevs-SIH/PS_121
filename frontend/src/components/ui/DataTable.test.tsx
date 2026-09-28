import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { DataTable, type Column } from './DataTable'

type Row = { id: number; name: string; d: number | null }
const rows: Row[] = [
  { id: 1, name: 'b', d: 20 },
  { id: 2, name: 'a', d: null },
  { id: 3, name: 'c', d: 5 },
]
const cols: Column<Row>[] = [
  { key: 'name', header: 'Name', render: (r) => r.name, sortValue: (r) => r.name },
  {
    key: 'd',
    header: 'Distance',
    render: (r) => r.d ?? '—',
    sortValue: (r) => r.d,
    align: 'right',
  },
  { key: 'x', header: 'Unsortable', render: () => 'x' },
]

const names = () =>
  screen
    .getAllByRole('row')
    .slice(1)
    .map((r) => within(r).getAllByRole('cell')[0]!.textContent)

describe('DataTable', () => {
  it('sorts by the initial column, nulls last, and toggles direction', async () => {
    render(
      <DataTable
        columns={cols}
        rows={rows}
        rowKey={(r) => r.id}
        initialSort={{ key: 'd', dir: 'asc' }}
      />,
    )
    expect(names()).toEqual(['c', 'b', 'a'])
    expect(screen.getByRole('columnheader', { name: /Distance/ })).toHaveAttribute(
      'aria-sort',
      'ascending',
    )
    await userEvent.click(screen.getByRole('button', { name: /Distance/ }))
    expect(names()).toEqual(['b', 'c', 'a'])
    await userEvent.click(screen.getByRole('button', { name: /Name/ }))
    expect(names()).toEqual(['a', 'b', 'c'])
    expect(
      within(screen.getByRole('columnheader', { name: 'Unsortable' })).queryByRole('button'),
    ).toBeNull()
  })

  it('reports row clicks and shows an empty message', async () => {
    const onRowClick = vi.fn()
    const { rerender } = render(
      <DataTable columns={cols} rows={rows} rowKey={(r) => r.id} onRowClick={onRowClick} />,
    )
    await userEvent.click(screen.getByText('c'))
    expect(onRowClick).toHaveBeenCalledWith(rows[2])
    rerender(<DataTable columns={cols} rows={[]} rowKey={(r) => r.id} empty="Nothing here" />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })
})
