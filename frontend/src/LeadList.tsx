import { Tabs } from "@base-ui/react/tabs";
import { useState } from "react";
import { api, type Lead, STATUSES } from "./api";
import { useLatestRequest } from "./useLatestRequest";

const SOURCE_LABEL: Record<Lead["source"], string> = {
  auto: "AI 발굴",
  report_form: "제보",
  report_assistant: "비서 제보",
};

export function LeadList({
  onSelect,
  refreshKey = 0,
  listLeads = api.listLeads,
}: {
  onSelect: (id: string) => void;
  refreshKey?: number;
  listLeads?: typeof api.listLeads;
}) {
  const [status, setStatus] = useState<string>("");
  const [q, setQ] = useState("");
  const { data, loading, error } = useLatestRequest((signal) => listLeads({ status, q }, signal), [status, q, refreshKey]);

  return (
    <section className="flex flex-col gap-3">
      <Tabs.Root value={status} onValueChange={(v) => setStatus(v as string)}>
        <Tabs.List className="flex flex-wrap gap-1">
          {["", ...STATUSES].map((s) => (
            <Tabs.Tab
              key={s || "all"}
              value={s}
              className="rounded-md px-3 py-1 text-sm text-slate-600 data-[selected]:bg-slate-900 data-[selected]:text-white"
            >
              {s || "전체"}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs.Root>
      <input
        className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        placeholder="제목·회사명 검색"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {error && <p className="text-sm text-red-600">목록을 불러오지 못했습니다.</p>}
      {/* 로딩 중에는 이전 결과를 유지한다. 빈 배열을 먼저 그리면 "0건"이 깜빡인다. */}
      {data && (
        <p className="text-sm text-slate-500" data-testid="count">
          {loading ? "불러오는 중…" : `${data.length}건`}
        </p>
      )}
      <ul className="divide-y divide-slate-200 rounded-md border border-slate-200">
        {data?.map((lead) => (
          <li key={lead.id}>
            <button className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-slate-50" onClick={() => onSelect(lead.id)}>
              <span className="w-16 shrink-0 text-xs text-slate-500">{SOURCE_LABEL[lead.source]}</span>
              <span className="flex-1 truncate">{lead.title}</span>
              <span className="text-xs text-slate-500">{lead.company_name ?? ""}</span>
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{lead.status}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
