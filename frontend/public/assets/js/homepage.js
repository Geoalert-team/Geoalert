/* =========================================================
   GeoAlert homepage scripts
   Only small, useful interactions:
   1. Mobile menu toggle
   2. Hero photo slider
   3. "Copy number" buttons for hotlines
   4. (Optional) load hotlines from the Django API later
   ========================================================= */

// ---- Settings ----
// When the Django endpoint exists, set USE_BACKEND to true.
// API_BASE_URL matches the backend's /api/... routes (see backend/config/urls.py).
const CONFIG = {
  API_BASE_URL: "http://localhost:8000/api",
  USE_BACKEND: false,
  SLIDE_INTERVAL_MS: 6000,
};

document.addEventListener("DOMContentLoaded", () => {
  setupMobileMenu();
  setupSlider();
  setupCopyButtons();
  setFooterYear();

  if (CONFIG.USE_BACKEND) {
    loadHotlines();
  }
});

/* ---------- 1. Mobile menu ---------- */
function setupMobileMenu() {
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.getElementById("site-nav");
  if (!toggle || !nav) return;

  toggle.addEventListener("click", () => {
    const isOpen = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!isOpen));
    nav.classList.toggle("is-open", !isOpen);
  });

  // Close the menu after a link is tapped
  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      toggle.setAttribute("aria-expanded", "false");
      nav.classList.remove("is-open");
    });
  });
}

/* ---------- 2. Hero slider ---------- */
function setupSlider() {
  const slider = document.querySelector("[data-slider]");
  if (!slider) return;

  const track = slider.querySelector(".slider-track");
  const slides = slider.querySelectorAll(".slide");
  const dots = slider.querySelectorAll(".slider-dot");
  let current = 0;
  let timer = null;

  // Slide the track left so the chosen photo is showing
  function showSlide(index) {
    dots[current].classList.remove("is-active");
    current = index;
    track.style.transform = `translateX(-${current * 100}%)`;
    dots[current].classList.add("is-active");
  }

  function next() {
    showSlide((current + 1) % slides.length);
  }

  function start() {
    stop();
    timer = setInterval(next, CONFIG.SLIDE_INTERVAL_MS);
  }

  function stop() {
    clearInterval(timer);
  }

  // Clicking a dot jumps to that photo and restarts the timer
  dots.forEach((dot, i) => {
    dot.addEventListener("click", () => {
      showSlide(i);
      start();
    });
  });

  // Pause while the mouse is over the photo
  slider.addEventListener("mouseenter", stop);
  slider.addEventListener("mouseleave", start);

  start();
}

/* ---------- 3. Copy hotline numbers ---------- */
function setupCopyButtons() {
  // Uses event delegation so it also works for hotlines loaded from the API
  const list = document.getElementById("hotline-list");
  if (!list) return;

  list.addEventListener("click", async (event) => {
    const button = event.target.closest(".btn-copy");
    if (!button) return;

    const number = button.dataset.copy;
    try {
      await navigator.clipboard.writeText(number);
      showCopied(button);
    } catch (error) {
      // Clipboard can fail on non-HTTPS pages; tell the user what to do instead
      button.textContent = "Select and copy the number";
    }
  });
}

function showCopied(button) {
  const original = "Copy number";
  button.textContent = "Copied";
  button.classList.add("is-copied");
  setTimeout(() => {
    button.textContent = original;
    button.classList.remove("is-copied");
  }, 2000);
}

/* ---------- 4. Load hotlines from Django (for later) ---------- */
// Expected JSON from the backend, for example GET /api/hotlines/ :
// [ { "name": "Talisay DRRMO", "number": "(032) 407-5928" }, ... ]
async function loadHotlines() {
  const list = document.getElementById("hotline-list");
  if (!list) return;

  try {
    const response = await fetch(`${CONFIG.API_BASE_URL}/hotlines/`);
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    const hotlines = await response.json();

    list.innerHTML = hotlines.map(hotlineCardHTML).join("");
  } catch (error) {
    // Keep the static list in the HTML if the API is unavailable
    console.warn("Could not load hotlines from the API. Showing the built-in list.", error);
  }
}

function hotlineCardHTML(hotline) {
  const name = escapeHTML(hotline.name);
  const number = escapeHTML(hotline.number);
  const telLink = toTelLink(hotline.number);
  return `
    <li class="hotline-card">
      <h3>${name}</h3>
      <a class="hotline-number" href="${telLink}">${number}</a>
      <button type="button" class="btn-copy" data-copy="${number}">Copy number</button>
    </li>`;
}

// "(032) 407-5928" -> "tel:+63324075928" (Philippine landline format)
function toTelLink(number) {
  const digits = String(number).replace(/\D/g, "");
  const withCountry = digits.startsWith("0") ? "63" + digits.slice(1) : digits;
  return `tel:+${withCountry}`;
}

function escapeHTML(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/* ---------- Footer year ---------- */
function setFooterYear() {
  const year = document.getElementById("year");
  if (year) year.textContent = new Date().getFullYear();
}