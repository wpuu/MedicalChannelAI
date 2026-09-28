import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Building2, CalendarClock, ChevronRight, Clock, Wallet } from 'lucide-react';
import type { FollowupStatus, NotFitReason, TodayActionCard } from '../types/opportunity';
import { PriorityBadge } from './PriorityBadge';
import { CustomerResourcePanel } from './CustomerResourcePanel';
import { AiDecisionPanel } from './AiDecisionPanel';
import { NotFitReasonDialog } from './NotFitReasonDialog';
import { Badge } from './Badge';
import {
  EMPTY_TEXT,
  FOLLOWUP_STATUS_LABEL,
  fmtCurrency,
  fmtDate,
  fmtLifecycleStage,
} from '../utils/format';

interface Props {
  card: TodayActionCard;
  onUpdateFollowup: (id: string, status: FollowupStatus, notFitReason?: NotFitReason) => void;
  onOpenOutreach: (id: string, title: string) => void;
  onSnooze: (id: string) => void;
}

const LIFECYCLE_DOT: Record<string, string> = {
  DEMAND_SIGNAL: 'bg-slate-400',
  REGISTRATION: 'bg-sky-500',
  BIDDING: 'bg-amber-500',
  AWARDED: 'bg-emerald-500',
  CONTRACT_EXECUTION: 'bg-indigo-500',
  MAINTENANCE_RENEWAL: 'bg-purple-500',
};

export function TodayActionCardView({ card, onUpdateFollowup, onOpenOutreach, onSnooze }: Props) {
  const [notFitOpen, setNotFitOpen] = useState(false);
  const { facts } = card;

  const deadlineLabel = facts.bid_deadline
    ? '投标截止'
    : facts.estimated_procurement_date
      ? '预计采购时间'
      : facts.registration_deadline
        ? '报名截止'
        : null;
  const deadlineValue = facts.bid_deadline || facts.estimated_procurement_date || facts.registration_deadline;

  return (
    <div className="relative rounded-2xl border border-slate-200 bg-white p-4 shadow-sm shadow-slate-200/50 sm:p-5">
      <NotFitReasonDialog
        open={notFitOpen}
        onCancel={() => setNotFitOpen(false)}
        onConfirm={(reason) => {
          onUpdateFollowup(card.opportunity_id, 'NOT_FIT', reason);
          setNotFitOpen(false);
        }}
      />

      {/* 第一层 */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="inline-flex h-7 items-center rounded-lg bg-slate-900 px-2.5 text-xs font-bold tracking-wide text-white">
            TOP {card.rank}
          </span>
          <PriorityBadge priority={card.priority} size="sm" />
        </div>
        <Badge className="border-slate-200 bg-slate-50 text-slate-600">
          {FOLLOWUP_STATUS_LABEL[card.followup.status]}
        </Badge>
      </div>

      {/* 第二层 */}
      <div className="mt-3.5 space-y-1.5">
        <div className="flex items-center gap-1.5 text-sm font-medium text-slate-500">
          <Building2 className="h-4 w-4 text-slate-400" />
          <span>{facts.hospital_name ?? EMPTY_TEXT}</span>
          {facts.department && <span className="text-slate-300">/</span>}
          {facts.department && <span>{facts.department}</span>}
        </div>
        <Link
          to={`/opportunity/${card.opportunity_id}`}
          className="block text-base font-semibold leading-snug text-slate-900 hover:text-blue-700 sm:text-lg"
        >
          {facts.project_name ?? EMPTY_TEXT}
        </Link>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-1 text-sm text-slate-600">
          <span className="inline-flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${facts.lifecycle_stage ? LIFECYCLE_DOT[facts.lifecycle_stage] : 'bg-slate-300'}`} />
            {fmtLifecycleStage(facts.lifecycle_stage)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Wallet className="h-3.5 w-3.5 text-slate-400" />
            {fmtCurrency(facts.budget_amount)}
          </span>
          {deadlineLabel && (
            <span className="inline-flex items-center gap-1.5">
              <CalendarClock className="h-3.5 w-3.5 text-slate-400" />
              {deadlineLabel}：{fmtDate(deadlineValue)}
            </span>
          )}
          {!deadlineLabel && (
            <span className="inline-flex items-center gap-1.5 text-slate-400">
              <Clock className="h-3.5 w-3.5" />
              暂无公开截止时间
            </span>
          )}
        </div>
      </div>

      {/* 第三层 */}
      <div className="mt-3.5">
        <CustomerResourcePanel context={card.customer_context} compact />
      </div>

      {/* 第四层 */}
      <div className="mt-3.5">
        <AiDecisionPanel status={card.model_decision_status} blockReason={card.model_block_reason} decision={card.decision} compact />
      </div>

      {/* 操作区 */}
      <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3.5">
        <Link
          to={`/opportunity/${card.opportunity_id}`}
          className="inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
        >
          查看详情
          <ChevronRight className="h-3.5 w-3.5" />
        </Link>
        <button
          onClick={() => onUpdateFollowup(card.opportunity_id, 'CONTACTED')}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          已联系
        </button>
        <button
          onClick={() => onUpdateFollowup(card.opportunity_id, 'REVIEWING')}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          继续跟进
        </button>
        <button
          onClick={() => setNotFitOpen(true)}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-rose-50 hover:text-rose-700"
        >
          不适合
        </button>
        <button
          onClick={() => onSnooze(card.opportunity_id)}
          className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          稍后提醒
        </button>
        <button
          onClick={() => onOpenOutreach(card.opportunity_id, facts.project_name ?? '该商机')}
          className="ml-auto rounded-lg border border-teal-300 bg-teal-50 px-3 py-1.5 text-xs font-medium text-teal-700 hover:bg-teal-100"
        >
          生成沟通话术
        </button>
      </div>
    </div>
  );
}
