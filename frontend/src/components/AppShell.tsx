import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Briefcase,
  UserSearch,
  CalendarCheck,
  HandCoins,
  ChevronDown,
} from 'lucide-react';
import { useActor } from '../context/ActorContext';
import styles from './AppShell.module.css';

const NAV_ITEMS = [
  { to: '/', label: 'Executive Dashboard', icon: LayoutDashboard },
  { to: '/requisitions', label: 'Requisitions & Applications', icon: Briefcase },
  { to: '/screening', label: 'Screening & Candidates', icon: UserSearch },
  { to: '/interviews', label: 'Interview Management', icon: CalendarCheck },
  { to: '/offers', label: 'Offers & Decisions', icon: HandCoins },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { actors, currentActorId, currentActor, setCurrentActorId } = useActor();

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <div className={styles.logoMark}>TF</div>
          <div>
            <div className={styles.brandName}>TalentFlow AI</div>
            <div className={styles.brandTag}>Recruitment Ops</div>
          </div>
        </div>
        <nav className={styles.nav}>
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
            >
              <Icon size={17} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className={styles.sidebarFooter}>
          <div className={styles.footerNote}>No authentication — demo attribution only</div>
        </div>
      </aside>
      <div className={styles.main}>
        <header className={styles.topbar}>
          <div />
          <div className={styles.actorPicker}>
            <span className={styles.actingAsLabel}>Acting as</span>
            <div className={styles.actorSelectWrap}>
              <select
                className={styles.actorSelect}
                value={currentActorId ?? ''}
                onChange={(e) => setCurrentActorId(e.target.value)}
              >
                {actors.map((a) => (
                  <option key={a.actor_id} value={a.actor_id}>
                    {a.full_name} — {a.role.replace('_', ' ')}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className={styles.actorChevron} />
            </div>
            {currentActor && <span className={styles.actorRoleBadge}>{currentActor.role.replace('_', ' ')}</span>}
          </div>
        </header>
        <main className={styles.content}>{children}</main>
      </div>
    </div>
  );
}
