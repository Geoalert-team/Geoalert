import React, { useState } from 'react';
import { tutorialsApi } from '../../api/tutorialsApi';
import ConfirmBox from './ConfirmBox';

/** The warning before a category goes, word for word as agreed (spec, Revision 2). */
export const categoryWarning = (name) =>
  `Are you sure you want to delete '${name}'? This action is permanent and will automatically delete all videos contained within this category.`;

/**
 * Delete a category with all its videos, after the warning. Used next to the
 * section's header and in the Add videos form's category picker.
 *
 *   category       { id, name }
 *   label          the button's text
 *   onDeleted()    the category and its videos are gone
 *   onError(text)  the delete failed; the message to show
 */
export default function DeleteCategoryButton({ category, label = 'Delete category', disabled = false, onDeleted, onError }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    try {
      await tutorialsApi.removeCategory(category.id);
      setOpen(false);
      onDeleted();
    } catch (err) {
      setOpen(false);
      onError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="wt-edit-btn wt-edit-btn-danger"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        {label}
      </button>
      {open && (
        <ConfirmBox
          title="Delete category"
          message={categoryWarning(category.name)}
          confirmLabel="Delete"
          danger
          busy={busy}
          onConfirm={confirm}
          onCancel={() => { if (!busy) setOpen(false); }}
        />
      )}
    </>
  );
}
