import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Lead } from "./api";
import { LeadList } from "./LeadList";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

const lead = (id: string): Lead => ({
  id, case_id: "C-1", category: "노무", source: "auto", title: `리드 ${id}`, summary: "",
  company_name: null, department: "자문1팀", status: "미확인", stage: null, version: 1, updated_at: "",
});

afterEach(cleanup);

describe("필터 변경 경쟁 상태 (회귀)", () => {
  it("늦게 도착한 이전 요청의 빈 응답이 최신 결과를 덮어쓰지 않는다", async () => {
    const pending: Record<string, ReturnType<typeof deferred<Lead[]>>> = {};
    const listLeads = ({ q = "" }: { q?: string }) => (pending[q] = deferred<Lead[]>()).promise;

    render(<LeadList onSelect={() => {}} listLeads={listLeads} />);
    const input = screen.getByPlaceholderText("제목·회사명 검색");

    // 검색어를 빠르게 바꿔 요청 두 개를 연달아 보낸다.
    fireEvent.change(input, { target: { value: "가" } });
    fireEvent.change(input, { target: { value: "가온" } });

    // 최신 요청이 먼저 오고, 오래된 요청(결과 0건)이 나중에 온다.
    await act(async () => pending["가온"].resolve([lead("a"), lead("b")]));
    await act(async () => pending["가"].resolve([]));

    expect(screen.getByTestId("count").textContent).toBe("2건");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("최신 요청이 진행 중일 때 0건을 먼저 그리지 않는다", async () => {
    const pending: ReturnType<typeof deferred<Lead[]>>[] = [];
    const listLeads = () => {
      const d = deferred<Lead[]>();
      pending.push(d);
      return d.promise;
    };
    render(<LeadList onSelect={() => {}} listLeads={listLeads} />);
    await act(async () => pending[0].resolve([lead("a")]));
    expect(screen.getByTestId("count").textContent).toBe("1건");

    fireEvent.change(screen.getByPlaceholderText("제목·회사명 검색"), { target: { value: "x" } });
    expect(screen.getByTestId("count").textContent).toBe("불러오는 중…");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });
});
