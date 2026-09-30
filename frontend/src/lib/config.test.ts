import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildInfo, fetchRuntimeConfig, parseRuntimeConfig } from './config'

afterEach(() => vi.unstubAllGlobals())

describe('runtime config (/config.json)', () => {
  it('keeps known string keys and defaults the rest', () => {
    expect(
      parseRuntimeConfig({
        mapTileUrl: 'https://tiles.example/{z}/{x}/{y}.png',
        grafanaUrl: ' https://grafana.example/d/smriti ',
        unknown: 'ignored',
        mapTileAttribution: 42,
      }),
    ).toEqual({
      mapTileUrl: 'https://tiles.example/{z}/{x}/{y}.png',
      mapTileAttribution: '',
      grafanaUrl: 'https://grafana.example/d/smriti',
    })
    expect(parseRuntimeConfig(null).grafanaUrl).toBe('')
    expect(parseRuntimeConfig('nope').mapTileUrl).toBe('')
  })

  it('links Grafana only for http(s) URLs', () => {
    expect(parseRuntimeConfig({ grafanaUrl: 'javascript:alert(1)' }).grafanaUrl).toBe('')
    expect(parseRuntimeConfig({ grafanaUrl: '/grafana' }).grafanaUrl).toBe('')
    expect(parseRuntimeConfig({ grafanaUrl: '' }).grafanaUrl).toBe('')
    expect(parseRuntimeConfig({ grafanaUrl: 'http://localhost:3000' }).grafanaUrl).toBe(
      'http://localhost:3000',
    )
  })

  it('falls back to defaults when the file is missing or unreadable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('not json', { status: 200 })),
    )
    expect(await fetchRuntimeConfig()).toEqual({
      mapTileUrl: '',
      mapTileAttribution: '',
      grafanaUrl: '',
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 404 })),
    )
    expect((await fetchRuntimeConfig()).grafanaUrl).toBe('')
  })
})

describe('build info', () => {
  it('reads the Docker build args', () => {
    expect(
      buildInfo({
        VITE_GIT_SHA: '02933a9',
        VITE_APP_VERSION: '0.6.0',
        VITE_BUILD_TIME: '2026-09-30T06:30:00Z',
      }),
    ).toEqual({ version: '0.6.0', commit: '02933a9', builtAt: '30 Sept 2026, 12:00 pm IST' })
  })

  it('says dev when nothing was injected', () => {
    expect(buildInfo({})).toEqual({ version: null, commit: 'dev', builtAt: null })
    expect(buildInfo({ VITE_APP_VERSION: 'dev', VITE_BUILD_TIME: 'garbage' })).toEqual({
      version: null,
      commit: 'dev',
      builtAt: null,
    })
  })
})
