import { useEffect, useRef, useState } from "react";

/**
 * 의존값이 바뀔 때마다 요청을 보내되, 마지막 요청의 응답만 화면에 반영한다.
 *
 * 필터를 빠르게 바꾸면 요청 A(전체) → B(미확인)가 연달아 나가는데,
 * 느린 A 가 B 보다 늦게 도착하면 화면이 A 결과로 덮인다. 반대로 빈 결과를
 * 돌려준 요청이 늦게 오면 실제로는 리드가 있는데 "0건"이 뜬다.
 * 요청마다 순번을 매기고, 현재 순번이 아닌 응답은 버린다.
 */
export function useLatestRequest<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: unknown[]) {
  const seq = useRef(0);
  const [state, setState] = useState<{ data: T | null; loading: boolean; error: Error | null }>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    const mine = ++seq.current;
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    fetcher(ctrl.signal).then(
      (data) => mine === seq.current && setState({ data, loading: false, error: null }),
      (error: Error) => mine === seq.current && error.name !== "AbortError" && setState((s) => ({ ...s, loading: false, error })),
    );
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
