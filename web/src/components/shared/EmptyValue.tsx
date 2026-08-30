export function EmptyValue({ label = '暂无公开信息' }: { label?: string }) {
  return <span className="text-slate-400">{label}</span>
}

export function OfficialText({
  value,
  empty = '暂无公开信息',
}: {
  value: string | number | null | undefined
  empty?: string
}) {
  if (value === null || value === undefined || value === '') {
    return <EmptyValue label={empty} />
  }
  return <span className="text-slate-800">{String(value)}</span>
}
