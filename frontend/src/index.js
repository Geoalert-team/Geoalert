import React from "react";
import ReactDOM from "react-dom/client";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./index.css";
import App from "./App";

// Leaving a map page mid-zoom crashed the app ("Cannot read properties of
// undefined (reading '_leaflet_pos')"): Leaflet finishes a zoom animation on
// a 250 ms timer that remove() does not cancel, and by then the map's panes
// are gone. Marking the zoom as over on remove makes that timer do nothing.
const removeMap = L.Map.prototype.remove;
L.Map.prototype.remove = function remove() {
  this._animatingZoom = false;
  return removeMap.call(this);
};

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
