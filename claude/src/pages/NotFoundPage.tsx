import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';

export function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-[1240px] flex-col items-center gap-3 px-4 py-24 text-center">
      <Compass className="h-10 w-10 text-slate-300" />
      <p className="text-base font-medium text-slate-700">页面不存在</p>
      <p className="text-sm text-slate-400">请返回今日行动页面继续查看商机</p>
      <Link to="/today" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white">
        返回今日行动
      </Link>
    </div>
  );
}
