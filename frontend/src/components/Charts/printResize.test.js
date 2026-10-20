import { installPrintResize } from './printResize';

test('every chart resizes before printing and again after', () => {
  const a = { resize: jest.fn() };
  const b = { resize: jest.fn() };
  const remove = installPrintResize({ instances: { 0: a, 1: b } });

  window.dispatchEvent(new Event('beforeprint'));
  expect(a.resize).toHaveBeenCalledTimes(1);
  expect(b.resize).toHaveBeenCalledTimes(1);

  window.dispatchEvent(new Event('afterprint'));
  expect(a.resize).toHaveBeenCalledTimes(2);

  remove();
  window.dispatchEvent(new Event('beforeprint'));
  expect(a.resize).toHaveBeenCalledTimes(2);
});
