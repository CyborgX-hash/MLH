interface Props {
  ok: boolean
  label: string
}

export function StatusBadge({ ok, label }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-medium ${
        ok ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
      }`}
    >
      <span aria-hidden className={`h-2 w-2 rounded-full ${ok ? 'bg-emerald-500' : 'bg-rose-500'}`} />
      {label}
    </span>
  )
}
