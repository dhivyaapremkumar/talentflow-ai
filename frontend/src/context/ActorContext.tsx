// "Acting as" selection — lets a user pick which SystemActor they are
// performing an action as, so the backend's hard role gates
// (requisition/offer approval) have a real actor_id + role to check.
// SystemActor carries no authentication (data_dictionary.md §18) - this
// is explicitly a demo/attribution convenience, never presented as login.
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { listActors } from '../api/resources';
import type { SystemActor } from '../types/api';

interface ActorContextValue {
  actors: SystemActor[];
  loading: boolean;
  currentActorId: string | null;
  currentActor: SystemActor | null;
  setCurrentActorId: (id: string) => void;
}

const ActorContext = createContext<ActorContextValue | null>(null);

const STORAGE_KEY = 'talentflow.currentActorId';

export function ActorProvider({ children }: { children: ReactNode }) {
  const [actors, setActors] = useState<SystemActor[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentActorId, setCurrentActorIdState] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY),
  );

  useEffect(() => {
    listActors()
      .then((list) => {
        setActors(list);
        setLoading(false);
        if (!currentActorId && list.length > 0) {
          setCurrentActorIdState(list[0].actor_id);
        }
      })
      .catch(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setCurrentActorId = (id: string) => {
    setCurrentActorIdState(id);
    localStorage.setItem(STORAGE_KEY, id);
  };

  const currentActor = useMemo(
    () => actors.find((a) => a.actor_id === currentActorId) ?? null,
    [actors, currentActorId],
  );

  return (
    <ActorContext.Provider value={{ actors, loading, currentActorId, currentActor, setCurrentActorId }}>
      {children}
    </ActorContext.Provider>
  );
}

export function useActor() {
  const ctx = useContext(ActorContext);
  if (!ctx) throw new Error('useActor must be used within an ActorProvider');
  return ctx;
}
