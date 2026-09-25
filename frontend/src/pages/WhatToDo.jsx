import React from 'react';
import PublicNavbar from '../components/Navbar/PublicNavbar';

export default function WhatToDo() {
  return (
    <div className="public-page">
      <PublicNavbar />
      <div className="simple-page">
        <h1>What To Do</h1>
        <p>Safety protocols and preparedness guidance for floods, landslides, and fires will appear here.</p>
      </div>
    </div>
  );
}