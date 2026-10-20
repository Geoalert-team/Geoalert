import React, { useEffect, useRef, useState } from 'react';

/**
 * One Export button for the three ways out of the Analytics tab. The caller
 * logs each to the audit log before acting, so `via` must stay one of
 * 'csv', 'pdf' or 'print'.
 *
 * Disabled while figures are reloading, so a file never mixes the old
 * numbers with the new filters.
 */

const CHOICES = [
  { via: 'csv', label: 'Download CSV' },
  { via: 'pdf', label: 'Save as PDF', title: 'Opens the print dialog. Choose "Save as PDF" as the printer.' },
  { via: 'print', label: 'Print' },
];

export default function ExportMenu({ onExport, disabled = false }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const buttonRef = useRef(null);
  const shown = open && !disabled;

  // Escape or a choice puts keyboard focus back where the menu was opened,
  // instead of dropping it to the top of the page. A click elsewhere leaves
  // focus wherever the person clicked.
  function close() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  // Disabling closes the menu for good, so it does not pop back open by
  // itself when the reload that disabled it finishes
  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    if (!shown) return undefined;
    // Same as close(), inline so the effect depends only on stable values
    function onKey(e) {
      if (e.key !== 'Escape') return;
      setOpen(false);
      buttonRef.current?.focus();
    }
    function onDown(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [shown]);

  function choose(via) {
    close();
    onExport(via);
  }

  return (
    <div className="an-export db-no-print" ref={ref}>
      <button
        ref={buttonRef}
        type="button"
        className="db-btn db-btn-outline db-btn-sm"
        aria-expanded={shown}
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
      >
        Export
      </button>
      {shown && (
        <div className="an-export-menu">
          {CHOICES.map((c) => (
            <button key={c.via} type="button" title={c.title} onClick={() => choose(c.via)}>
              {c.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
