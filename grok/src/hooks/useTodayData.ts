import { useCallback, useEffect, useState } from "react";
import { todayActionsService } from "@/services";
import { DATA_CHANGED_EVENT } from "@/services/events";
import type {
  CardActionState,
  FollowUpRecord,
  TodayActionCard,
  TodayActionsSummary,
} from "@/types/today-actions";

export function useTodayData() {
  const [summary, setSummary] = useState<TodayActionsSummary | null>(null);
  const [cards, setCards] = useState<TodayActionCard[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    todayActionsService.getTodayPayload().then((payload) => {
      if (cancelled) return;
      setSummary(payload.summary);
      setCards(payload.cards);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { summary, cards, loading };
}

export function useOpportunity(id: string | undefined) {
  const [card, setCard] = useState<TodayActionCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (!id) {
      setMissing(true);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    todayActionsService.getOpportunity(id).then((found) => {
      if (cancelled) return;
      setCard(found);
      setMissing(!found);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return { card, loading, missing };
}

export function useFollowUps(opportunityId: string | undefined) {
  const [records, setRecords] = useState<FollowUpRecord[]>([]);
  const [actionState, setActionState] = useState<CardActionState>({
    action: null,
    remind_at: null,
    updated_at: null,
  });

  const reload = useCallback(async () => {
    if (!opportunityId) return;
    const [list, state] = await Promise.all([
      todayActionsService.getFollowUps(opportunityId),
      todayActionsService.getActionState(opportunityId),
    ]);
    setRecords(list);
    setActionState(state);
  }, [opportunityId]);

  useEffect(() => {
    void reload();
    const onChange = () => {
      void reload();
    };
    window.addEventListener(DATA_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(DATA_CHANGED_EVENT, onChange);
  }, [reload]);

  return { records, actionState, reload };
}

export function useActionStates(ids: string[]) {
  const [map, setMap] = useState<Record<string, CardActionState>>({});
  const idKey = ids.join(",");

  useEffect(() => {
    let cancelled = false;
    const list = idKey ? idKey.split(",") : [];
    const reload = async () => {
      if (list.length === 0) return;
      const entries = await Promise.all(
        list.map(async (id) => [id, await todayActionsService.getActionState(id)] as const),
      );
      if (cancelled) return;
      const next: Record<string, CardActionState> = {};
      for (const [id, state] of entries) next[id] = state;
      setMap(next);
    };
    void reload();
    const onChange = () => {
      void reload();
    };
    window.addEventListener(DATA_CHANGED_EVENT, onChange);
    return () => {
      cancelled = true;
      window.removeEventListener(DATA_CHANGED_EVENT, onChange);
    };
  }, [idKey]);

  return map;
}
