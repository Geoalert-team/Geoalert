import React from 'react';
import { ConfirmDialog } from '../../pages/Dashboard/admin/adminShared';
import '../../pages/css/Dashboard.css';
import '../../pages/css/AdminDashboard.css';

/**
 * The admin dashboard's confirmation dialog, on the public What To Do page
 * instead of the browser's own confirm box. Its styles live under .db-scope
 * (the dashboard tokens) and .adm, both scoped, so the wrapper carries them.
 * Takes ConfirmDialog's props: title, message, confirmLabel, danger, busy,
 * onConfirm, onCancel.
 */
export default function ConfirmBox(props) {
  return (
    <div className="db-scope adm">
      <ConfirmDialog {...props} />
    </div>
  );
}
