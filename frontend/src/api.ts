export type LeadStatus = "미확인" | "연락함" | "관심있음" | "보류" | "제외" | "배당";
export const STATUSES: LeadStatus[] = ["미확인", "연락함", "관심있음", "보류", "제외", "배당"];

export interface Lead {
  id: string;
  case_id: string;
  category: string;
  source: "report_form" | "report_assistant" | "auto";
  title: string;
  summary: string;
  company_name: string | null;
  department: string;
  status: LeadStatus;
  stage: string | null;
  version: number;
  updated_at: string;
}

export interface LeadDetail extends Lead {
  human_edited: string[];
  evidence: { id: string; quote: string; source_ref: string }[];
}

export class ConflictError extends Error {
  constructor(public current: Lead) {
    super("conflict");
  }
}

// 데모용 인증. 운영에서는 SSO 세션이 이 자리를 대신한다.
let userId = "1";
export const setUser = (id: string) => (userId = id);

async function call<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    signal,
    headers: { "Content-Type": "application/json", "X-User-Id": userId, ...init.headers },
  });
  if (res.status === 409) throw new ConflictError((await res.json()).detail.current);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

export const api = {
  listLeads: (params: { status?: string; q?: string }, signal?: AbortSignal) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
    return call<{ items: Lead[] }>(`/leads?${qs}`, {}, signal).then((r) => r.items);
  },
  getLead: (id: string) => call<LeadDetail>(`/leads/${id}`),
  patchLead: (id: string, base: Lead, changes: Partial<Lead>) =>
    call<Lead>(`/leads/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        base_version: base.version,
        changes,
        // 내가 본 값. 서버는 그 사이 이 값이 안 바뀌었으면 병합한다.
        base_values: Object.fromEntries(Object.keys(changes).map((k) => [k, base[k as keyof Lead]])),
      }),
    }),
};
