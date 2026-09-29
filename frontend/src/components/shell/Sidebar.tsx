import { ChevronsLeft, ChevronsRight } from 'lucide-react'
import { motion } from 'motion/react'
import { useId, useMemo } from 'react'
import { Link, NavLink, useLocation, useSearchParams } from 'react-router'

import { screensFor, type ScreenSpec } from '../../app/screens'
import { useWells } from '../../lib/api/hooks'
import { cn } from '../../lib/cn'
import { activePillTransition } from '../../lib/motion'
import { FLUID_ORDER, FLUIDS, type FluidType } from '../../lib/wellTypes'
import { useUiStore } from '../../stores/ui'

const GROUPS: { title: string; ids: string[] }[] = [
  { title: 'Overview', ids: ['dashboard', 'map'] },
  { title: 'Knowledge', ids: ['search', 'well360', 'correlation', 'ledger'] },
  { title: 'Operations', ids: ['live', 'alerts'] },
  { title: 'Data', ids: ['documents', 'analytics', 'admin', 'system'] },
]

interface Props {
  collapsed: boolean
  /** Rendered inside the mobile drawer: always expanded, closes on navigation. */
  drawer?: boolean
  /** False when the rail is imposed (narrow window, full-bleed page): no toggle then. */
  canToggle?: boolean
}

export function Sidebar({ collapsed, drawer = false, canToggle = true }: Props) {
  const mode = useUiStore((s) => s.mode)
  const setCollapsed = useUiStore((s) => s.setSidebarCollapsed)
  const setMobileNavOpen = useUiStore((s) => s.setMobileNavOpen)
  const setWellType = useUiStore((s) => s.setWellType)
  const wellType = useUiStore((s) => s.wellType)
  const pillId = useId()
  const location = useLocation()
  const [params] = useSearchParams()
  const wells = useWells()
  const screens = useMemo(() => new Map(screensFor(mode).map((s) => [s.id, s])), [mode])

  const counts = useMemo(() => {
    const c: Record<FluidType, number> = { oil: 0, gas: 0, water: 0 }
    for (const w of wells.data?.items ?? []) {
      if (w.fluid_type === 'oil' || w.fluid_type === 'gas' || w.fluid_type === 'water')
        c[w.fluid_type] += 1
    }
    return c
  }, [wells.data])

  const close = () => drawer && setMobileNavOpen(false)
  const onMap = location.pathname === '/map'
  const typeParam = params.get('type')

  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-1 overflow-x-hidden overflow-y-auto">
      <Link
        to="/"
        onClick={close}
        className="mb-2 flex h-14 shrink-0 items-center gap-3 px-4"
        aria-label="SMRITI home"
      >
        <span
          aria-hidden
          className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent font-mono text-sm font-bold text-accent-contrast"
        >
          S
        </span>
        <span
          className={cn(
            'min-w-0 transition-opacity duration-200',
            collapsed && 'pointer-events-none opacity-0',
          )}
        >
          <span className="block text-base leading-tight font-bold tracking-tight text-text">
            SMRITI
          </span>
          <span className="block truncate text-[0.7rem] text-muted">
            eRTMAC-NWIS · offset intelligence
          </span>
        </span>
      </Link>

      {GROUPS.map((g) => {
        const items = g.ids.map((id) => screens.get(id)).filter(Boolean) as ScreenSpec[]
        if (items.length === 0) return null
        return (
          <div key={g.title} className="px-2 pb-2">
            <p
              className={cn(
                'px-3 pb-1 text-[0.65rem] font-semibold tracking-wider text-muted uppercase transition-opacity',
                collapsed && 'opacity-0',
              )}
              aria-hidden={collapsed}
            >
              {g.title}
            </p>
            <ul className="space-y-0.5">
              {items.map((s) => (
                <li key={s.id}>
                  <NavItem
                    screen={s}
                    collapsed={collapsed}
                    pillId={pillId}
                    onNavigate={close}
                    forceInactive={s.id === 'map' && onMap && Boolean(typeParam)}
                  />
                </li>
              ))}
              {g.title === 'Overview' && (
                <li className="pt-1">
                  <ul aria-label="Wells by fluid" className="space-y-0.5">
                    {FLUID_ORDER.map((f) => {
                      const meta = FLUIDS[f]
                      const active = onMap && typeParam === f
                      return (
                        <li key={f}>
                          <NavLink
                            to={`/map?type=${f}`}
                            onClick={() => {
                              setWellType(f)
                              close()
                            }}
                            title={collapsed ? `${meta.plural} (${counts[f]})` : undefined}
                            aria-current={active ? 'page' : undefined}
                            className={cn(
                              'group relative flex h-9 items-center gap-3 rounded-lg px-3 text-sm',
                              active
                                ? 'text-text'
                                : 'text-muted hover:bg-surface-2 hover:text-text',
                            )}
                          >
                            {active && (
                              <motion.span
                                layoutId={`${pillId}-pill`}
                                transition={activePillTransition}
                                className="absolute inset-0 rounded-lg bg-surface-2 ring-1 ring-border"
                                aria-hidden
                              />
                            )}
                            <motion.span
                              whileHover={{ scale: 1.08 }}
                              className={cn('relative shrink-0', meta.textClass)}
                            >
                              <meta.icon size={18} aria-hidden />
                            </motion.span>
                            <span
                              className={cn(
                                'relative flex-1 truncate transition-opacity',
                                collapsed && 'opacity-0',
                              )}
                            >
                              {meta.plural}
                            </span>
                            <span
                              className={cn(
                                'num relative rounded-full px-1.5 text-[0.7rem] transition-opacity',
                                wellType === f ? 'bg-surface text-text' : 'text-muted',
                                collapsed && 'opacity-0',
                              )}
                              data-testid={`well-count-${f}`}
                            >
                              {counts[f]}
                            </span>
                          </NavLink>
                        </li>
                      )
                    })}
                  </ul>
                </li>
              )}
            </ul>
          </div>
        )
      })}

      {!drawer && canToggle && (
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          data-testid="sidebar-toggle"
          className="mx-2 mt-auto mb-3 flex h-9 items-center gap-3 rounded-lg px-3 text-sm text-muted hover:bg-surface-2 hover:text-text"
        >
          {collapsed ? <ChevronsRight size={18} /> : <ChevronsLeft size={18} />}
          <span className={cn('transition-opacity', collapsed && 'opacity-0')}>Collapse</span>
        </button>
      )}
    </nav>
  )
}

function NavItem({
  screen,
  collapsed,
  pillId,
  onNavigate,
  forceInactive,
}: {
  screen: ScreenSpec
  collapsed: boolean
  pillId: string
  onNavigate: () => void
  forceInactive: boolean
}) {
  const Icon = screen.icon
  const planned = screen.status !== 'built'
  return (
    <NavLink
      to={screen.navPath}
      end={screen.navPath === '/'}
      onClick={onNavigate}
      title={collapsed ? screen.title : undefined}
      data-screen={screen.id}
      data-title={screen.title}
      className={({ isActive }) =>
        cn(
          'group relative flex h-9 items-center gap-3 rounded-lg px-3 text-sm',
          isActive && !forceInactive
            ? 'font-medium text-text'
            : 'text-muted hover:bg-surface-2 hover:text-text',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && !forceInactive && (
            <motion.span
              layoutId={`${pillId}-pill`}
              transition={activePillTransition}
              className="absolute inset-0 rounded-lg bg-surface-2 ring-1 ring-border"
              aria-hidden
            >
              <span className="absolute top-1.5 bottom-1.5 left-0 w-0.5 rounded-full bg-accent" />
            </motion.span>
          )}
          <motion.span whileHover={{ scale: 1.08 }} className="relative shrink-0">
            <Icon
              size={18}
              aria-hidden
              className={isActive && !forceInactive ? 'text-accent' : ''}
            />
          </motion.span>
          <span
            className={cn('relative flex-1 truncate transition-opacity', collapsed && 'opacity-0')}
          >
            {screen.title}
          </span>
          {planned && (
            <span
              className={cn(
                'relative text-[0.65rem] text-muted opacity-70 transition-opacity',
                collapsed && 'opacity-0',
              )}
              aria-label={`planned ${screen.phase}`}
            >
              {screen.phase}
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}
