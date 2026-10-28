import { useState } from "react";
import { api, ConflictError, type LeadDetail as Detail, type LeadStatus, STATUSES } from "./api";
import { useLatestRequest } from "./useLatestRequest";

export function LeadDetail({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [reload, setReload] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const { data: lead } = useLatestRequest<Detail>(() => api.getLead(id), [id, reload]);

  if (!lead) return null;

  async function changeStatus(status: LeadStatus) {
    try {
      await api.patchLead(lead!.id, lead!, { status });
      setNotice(null);
    } catch (e) {
      if (!(e instanceof ConflictError)) throw e;
      setNotice("다른 사람이 먼저 상태를 바꿨습니다. 최신 내용으로 다시 불러왔습니다.");
    }
    setReload((n) => n + 1);
    onChanged();
  }

  return (
    <article className="flex flex-col gap-3 rounded-md border border-slate-200 p-4">
      <header>
        <p className="text-xs text-slate-500">
          {lead.category} · {lead.department} · 사건 {lead.case_id}
        </p>
        <h2 className="text-lg font-semibold">{lead.title}</h2>
        {lead.company_name && <p className="text-sm">{lead.company_name}</p>}
      </header>
      {notice && <p className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">{notice}</p>}
      <div className="flex flex-wrap gap-1">
        {STATUSES.map((s) => (
          <button
            key={s}
            disabled={s === lead.status}
            onClick={() => changeStatus(s)}
            className="rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-900 disabled:text-white"
          >
            {s}
          </button>
        ))}
      </div>
      <section>
        <h3 className="mb-1 text-sm font-medium">근거 원문</h3>
        <ul className="flex flex-col gap-2">
          {lead.evidence.map((e) => (
            <li key={e.id} className="border-l-2 border-slate-300 pl-3 text-sm">
              “{e.quote}”<span className="ml-2 text-xs text-slate-400">{e.source_ref}</span>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
