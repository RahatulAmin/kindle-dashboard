import type { ReactNode } from 'react'

export const pages = {
  overview: 'Overview',
  tasks: 'Tasks',
  deadlines: 'Deadlines',
  pomodoro: 'Pomodoro',
  photos: 'Photo Library',
  display: 'Display',
  'prayer-times': 'Prayer Times',
  briefing: 'Briefing',
  audit: 'API Audit',
  settings: 'Settings',
  widgets: 'Widgets',
} as const

export type Page = keyof typeof pages

export function AdminShell({ page, children, account }: {
  page: Page; children: ReactNode; account: ReactNode;
}) {
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[15rem_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only">Skip to content</a>
      <aside className="border-b border-slate-800 bg-slate-950 px-5 py-6 text-white md:border-b-0">
        <div className="mb-6 flex items-center gap-3">
          <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-md border-2 border-teal-300">
            <span className="h-2 w-4 border-y border-teal-300" />
          </span>
          <span className="font-semibold tracking-tight">Kindle Dashboard</span>
        </div>
        <nav aria-label="Administration" className="flex flex-wrap gap-1 md:flex-col">
          {Object.entries(pages).map(([key, title]) => (
            <a key={key} href={'#/' + key} aria-current={key === page ? 'page' : undefined}
              className={'rounded-md px-3 py-2 text-sm font-medium ' +
                (key === page ? 'bg-teal-300 text-slate-950' : 'text-slate-300 hover:bg-slate-800')}>
              {title}
            </a>
          ))}
        </nav>
        {account}
      </aside>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl px-5 py-9 sm:px-10 md:py-14">
        {children}
      </main>
    </div>
  )
}
