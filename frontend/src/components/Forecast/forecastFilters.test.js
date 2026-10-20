import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import SeasonalOutlook from './SeasonalOutlook';
import BarangayLikelihood from './BarangayLikelihood';
import { historyApi } from '../../api/historyApi';
import { buildRiskOutlook } from '../../utils/riskOutlook';

jest.mock('../../api/historyApi', () => ({
  historyApi: { list: jest.fn(), forecast: jest.fn() },
}));
jest.mock('../../utils/riskOutlook', () => ({ buildRiskOutlook: jest.fn(() => null) }));

beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
beforeEach(() => { jest.clearAllMocks(); });

const records = [{ id: 1, is_sample: true }, { id: 2, is_sample: false }];

async function render(node) {
  const el = document.createElement('div');
  await act(async () => { createRoot(el).render(node); });
  return el;
}

test('outlook reads one hazard type and leaves sample records out', async () => {
  historyApi.list.mockResolvedValue(records);
  await render(<SeasonalOutlook hazardTypeId="2" hazardName="Flood" includeSamples={false} />);
  expect(historyApi.list).toHaveBeenCalledWith({ hazard_type: '2' });
  expect(buildRiskOutlook).toHaveBeenLastCalledWith([{ id: 2, is_sample: false }]);
});

test('outlook keeps sample records when asked, and names the scope', async () => {
  historyApi.list.mockResolvedValue(records);
  const el = await render(<SeasonalOutlook hazardTypeId="" hazardName={null} includeSamples />);
  expect(historyApi.list).toHaveBeenCalledWith({});
  expect(buildRiskOutlook).toHaveBeenLastCalledWith(records);
  expect(el.textContent).toContain('From the whole archive for all hazard types. The period above does not apply.');
});

test('outlook says so when it cannot load', async () => {
  historyApi.list.mockRejectedValue(new Error('down'));
  const el = await render(<SeasonalOutlook hazardTypeId="" hazardName={null} includeSamples={false} />);
  expect(el.textContent).toContain('The seasonal outlook could not be loaded right now.');
});

test('likelihood takes its hazard from outside and can leave samples out', async () => {
  historyApi.forecast.mockResolvedValue({ results: [], years: [], basis: { records: 0, sample_records: 0 } });
  const el = await render(<BarangayLikelihood hazard="Flood" excludeSamples />);
  expect(historyApi.forecast).toHaveBeenCalledWith(expect.objectContaining({
    hazard_type_name: 'Flood', exclude_samples: 'true',
  }));
  expect(el.querySelectorAll('select')).toHaveLength(1); // the month picker only
});
