/** Test double for src/lib/maplibre (jsdom has no WebGL). Keeps enough behaviour for the
 *  WellMap component to be exercised: sources hold data, querySourceFeatures returns the
 *  points, markers are real DOM elements appended to the container. */
type Handler = (...args: unknown[]) => void

interface Feature {
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: Record<string, unknown>
}

export class GeoJSONSource {
  data: { features: Feature[] } = { features: [] }
  setData(d: { features: Feature[] }) {
    this.data = d
    return this
  }
  async getClusterExpansionZoom() {
    return 12
  }
}

export class LngLatBounds {
  private points: [number, number][] = []
  extend(p: [number, number]) {
    this.points.push(p)
    return this
  }
  isEmpty() {
    return this.points.length === 0
  }
}

export class Map {
  static instances: Map[] = []
  container: HTMLElement
  handlers: Record<string, Handler[]> = {}
  sources: Record<string, GeoJSONSource> = {}
  layers: string[] = []
  paint: Record<string, unknown> = {}
  flights: unknown[] = []
  removed = false

  constructor(opts: { container: HTMLElement }) {
    this.container = opts.container
    Map.instances.push(this)
    setTimeout(() => this.emit('load'), 0)
  }
  emit(evt: string) {
    for (const h of this.handlers[evt] ?? []) h()
  }
  on(evt: string, h: Handler) {
    ;(this.handlers[evt] ??= []).push(h)
    return this
  }
  once(evt: string, h: Handler) {
    return this.on(evt, h)
  }
  addControl() {
    return this
  }
  addSource(id: string, spec: { data?: { features: Feature[] } }) {
    const s = new GeoJSONSource()
    if (spec.data) s.setData(spec.data)
    this.sources[id] = s
  }
  getSource(id: string) {
    return this.sources[id]
  }
  addLayer(l: { id: string }) {
    this.layers.push(l.id)
  }
  setPaintProperty(layer: string, prop: string, value: unknown) {
    this.paint[`${layer}.${prop}`] = value
  }
  querySourceFeatures(id: string) {
    return this.sources[id]?.data.features ?? []
  }
  cameraForBounds() {
    return { center: [95.25, 27.4], zoom: 11 }
  }
  flyTo(opts: unknown) {
    this.flights.push(opts)
  }
  easeTo() {}
  resize() {}
  remove() {
    this.removed = true
  }
}

export class Marker {
  element: HTMLElement
  constructor(opts: { element: HTMLElement }) {
    this.element = opts.element
  }
  setLngLat() {
    return this
  }
  addTo(map: Map) {
    map.container.appendChild(this.element)
    return this
  }
  getElement() {
    return this.element
  }
  remove() {
    this.element.remove()
  }
}

export class NavigationControl {}
export class ScaleControl {}
