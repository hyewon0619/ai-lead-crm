import { useState } from "react";
import { setUser } from "./api";
import { LeadDetail } from "./LeadDetail";
import { LeadList } from "./LeadList";

// 합성 데이터(scripts/generate_sample_data.py)의 데모 계정
const DEMO_USERS = [
  ["1", "관리자"],
  ["10", "검토자1 (기업자문1팀)"],
  ["20", "직원1 (기업자문1팀)"],
];

export function App() {
  const [selected, setSelected] = useState<string | null>(null);
  const [session, setSession] = useState(0);
  const [refresh, setRefresh] = useState(0);

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-4 p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold">AI Lead CRM</h1>
        <select
          className="rounded border border-slate-300 px-2 py-1 text-sm"
          onChange={(e) => {
            setUser(e.target.value);
            setSelected(null);
            setSession((n) => n + 1);
          }}
        >
          {DEMO_USERS.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </header>
      <div className="grid gap-4 md:grid-cols-[1fr_1fr]">
        <LeadList key={session} refreshKey={refresh} onSelect={setSelected} />
        {selected && <LeadDetail id={selected} onChanged={() => setRefresh((n) => n + 1)} />}
      </div>
    </main>
  );
}
