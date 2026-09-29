import { render, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { Providers } from '../../app/providers'
import { makeQueryClient } from '../../app/queryClient'
import { Map as FakeMap } from '../../test/fakeMaplibre'
import { CONFIG, mockBackend } from '../../test/utils'
import WellMap, { type MapWell } from './WellMap'

const WELLS: MapWell[] = [
  { id: 1, name: 'A', lat: 27.4, lon: 95.25, status: 'completed', fluid: 'oil', role: 'active' },
  { id: 2, name: 'B', lat: 27.41, lon: 95.26, status: 'drilling', fluid: 'gas', role: 'offset' },
  {
    id: 3,
    name: 'C',
    lat: 27.45,
    lon: 95.3,
    status: 'planned',
    fluid: null,
    role: 'other',
    dimmed: true,
  },
]

function renderMap(props: Partial<Parameters<typeof WellMap>[0]> = {}) {
  mockBackend({ '/config.json': CONFIG })
  return render(
    <Providers client={makeQueryClient()}>
      <div style={{ width: 400, height: 300 }}>
        <WellMap wells={WELLS} {...props} />
      </div>
    </Providers>,
  )
}

describe('WellMap (MapLibre)', () => {
  it('draws one marker per well with role, fluid colour and a pulse for drilling wells', async () => {
    const { container } = renderMap({ active: { lat: 27.4, lon: 95.25 }, radiusKm: 5 })
    await waitFor(() => expect(container.querySelectorAll('.well-marker')).toHaveLength(3))
    const [a, b, c] = Array.from(container.querySelectorAll<HTMLElement>('.well-marker'))
    expect(a!.dataset.role).toBe('active')
    expect(a!.style.getPropertyValue('--c')).toBe('var(--well-oil)')
    expect(b!.dataset.live).toBe('true')
    expect(c!.dataset.dimmed).toBe('true')
    expect(c!.style.getPropertyValue('--c')).toBe('var(--accent-2)')
    expect(b!.getAttribute('aria-label')).toBe('B · drilling · gas')
  })

  it('draws the radius circle, flies to it and reports clicks', async () => {
    const onSelect = vi.fn()
    const { container } = renderMap({ active: { lat: 27.4, lon: 95.25 }, radiusKm: 5, onSelect })
    await waitFor(() => expect(container.querySelectorAll('.well-marker')).toHaveLength(3))
    const map = FakeMap.instances.at(-1)!
    const ring = map.sources.radius!.data.features
    expect(ring).toHaveLength(1)
    expect(map.flights.length).toBeGreaterThan(0)
    expect(map.paint['radius-line.line-color']).toBeDefined()
    await userEvent.click(container.querySelector('[data-well-id="2"]')!)
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('cleans up the map on unmount', async () => {
    const { unmount, container } = renderMap()
    await waitFor(() => expect(container.querySelectorAll('.well-marker')).toHaveLength(3))
    const map = FakeMap.instances.at(-1)!
    unmount()
    expect(map.removed).toBe(true)
  })
})
