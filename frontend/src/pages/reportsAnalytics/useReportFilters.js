import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { defaultFilters, filtersFromParams, filtersToParams } from './filters';

/**
 * [filters, setFilters(patch), resetFilters()] kept in the address, with the
 * presets of `kind` ('reports' or 'trends'). Filter changes replace the
 * history entry, so Back leaves the page rather than stepping through every
 * choice.
 */
export default function useReportFilters(kind = 'reports') {
  const [params, setParams] = useSearchParams();
  const key = params.toString();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const filters = useMemo(() => filtersFromParams(params, kind), [key, kind]);

  const setFilters = useCallback((patch) => {
    setParams((prev) => filtersToParams({ ...filtersFromParams(prev, kind), ...patch }, prev, kind), { replace: true });
  }, [setParams, kind]);

  const resetFilters = useCallback(() => {
    setParams((prev) => filtersToParams(defaultFilters(kind), prev, kind), { replace: true });
  }, [setParams, kind]);

  return [filters, setFilters, resetFilters];
}
