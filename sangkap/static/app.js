// Sangkap. Every page works without JavaScript; this file only adds extras.
"use strict";

// ---------- Light / dark theme ----------
// With no saved choice, the page follows the system setting (CSS does that).
// Pressing the button saves the opposite of what is showing now.

function currentTheme() {
  const saved = document.documentElement.dataset.theme;
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function updateThemeButton(button) {
  const next = currentTheme() === "dark" ? "light" : "dark";
  button.setAttribute("aria-label", `Switch to ${next} mode`);
  button.title = `Switch to ${next} mode`;
}

function setUpThemeToggle() {
  const button = document.getElementById("theme-toggle");
  if (!button) return;
  updateThemeButton(button);
  button.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch (e) {
      // Private windows can block storage; the theme still changes for this page.
    }
    updateThemeButton(button);
  });
}

// ---------- The ☰ menu on phones ----------
// The button opens and closes the menu. Escape closes it too. On computers
// the menu is a sidebar that is always open, and the button is hidden.

function setUpMenu() {
  const menu = document.querySelector("[data-menu]");
  const button = document.querySelector("[data-menu-button]");
  if (!menu || !button) return;
  const setOpen = (open) => {
    menu.classList.toggle("is-open", open);
    button.setAttribute("aria-expanded", String(open));
    button.setAttribute("aria-label", open ? "Close the menu" : "Menu");
  };
  button.addEventListener("click", () => setOpen(!menu.classList.contains("is-open")));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu.classList.contains("is-open")) {
      setOpen(false);
      button.focus();
    }
  });
}

// ---------- Install on a phone ----------
// The service worker (/sw.js) makes Sangkap installable. Browsers that can
// install it fire "beforeinstallprompt"; then every "Install app" button
// (data-install: in the sidebar and in Settings) shows. iPhones never fire
// it, so Settings also explains Safari's "Add to Home Screen".

function setUpInstall() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Not a problem: the site works the same without it.
    });
  }
  const buttons = Array.from(document.querySelectorAll("[data-install]"));
  if (!buttons.length) return;
  let offer = null;
  const show = (visible) => buttons.forEach((button) => { button.hidden = !visible; });
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // we show our own button instead of the browser's banner
    offer = event;
    show(true);
  });
  buttons.forEach((button) => button.addEventListener("click", async () => {
    if (!offer) return;
    offer.prompt();
    await offer.userChoice;
    offer = null;
    show(false);
  }));
  window.addEventListener("appinstalled", () => show(false));
}

// ---------- "Are you sure?" before deleting ----------
// A form with data-confirm="Question?" asks first. Without JavaScript it just sends.

function setUpConfirms() {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
}

// ---------- Filters that apply at once ----------
// A form with data-autosubmit sends itself when a menu or checkbox changes.
// Text boxes wait for Enter (or the button): sending on every change would
// reload the page as soon as you click away.

function setUpAutosubmit() {
  document.querySelectorAll("form[data-autosubmit]").forEach((form) => {
    form.addEventListener("change", (event) => {
      const box = event.target;
      if (box.tagName === "SELECT" || box.type === "checkbox" || box.type === "radio") {
        form.requestSubmit();
      }
    });
  });
}

// ---------- "What can I cook?": count what's picked ----------

function setUpPicker() {
  const form = document.querySelector("form[data-picker]");
  if (!form) return;
  const count = form.querySelector("[data-picked-count]");
  form.addEventListener("change", () => {
    const n = form.querySelectorAll("input[name=have]:checked").length;
    count.textContent = n === 0 ? "Nothing picked yet" : `${n} ingredient${n === 1 ? "" : "s"} picked`;
  });
}

// ---------- Meal plan: the ⋯ menus ----------
// They are <details>, so they open without JavaScript. This closes the
// others when one opens, and closes them on a click outside or Escape.

function setUpMealMenus() {
  const menus = Array.from(document.querySelectorAll("details.meal-menu"));
  if (!menus.length) return;
  const closeAll = (except) => menus.forEach((menu) => {
    if (menu !== except) menu.open = false;
  });
  menus.forEach((menu) => menu.addEventListener("toggle", () => {
    if (menu.open) closeAll(menu);
  }));
  document.addEventListener("click", (event) => {
    if (!event.target.closest("details.meal-menu")) closeAll(null);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAll(null);
  });
}

// ---------- Recipe form: add, remove and move rows ----------
// Without JavaScript the form still works: it shows a few empty rows, and
// "More rows" sends the form to get more. With it, rows are added here.

function renumberSteps(list) {
  list.querySelectorAll(".step-row").forEach((row, index) => {
    const number = row.querySelector(".step-number");
    if (number) number.textContent = index + 1;
    const box = row.querySelector("textarea");
    if (box) box.setAttribute("aria-label", `Step ${index + 1}`);
  });
}

function addRow(list, templateId) {
  const template = document.getElementById(templateId);
  if (!template) return null;
  const row = template.content.firstElementChild.cloneNode(true);
  list.appendChild(row);
  renumberSteps(list);
  const first = row.querySelector("input:not([type=hidden]), textarea");
  if (first) first.focus();
  return row;
}

function setUpRowEditing() {
  document.querySelectorAll("[data-add-row]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const list = document.getElementById(button.dataset.list);
      addRow(list, button.dataset.addRow);
    });
  });

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".row-tools button[data-action]");
    if (!button) return;
    event.preventDefault();
    const row = button.closest(".ingredient-row, .step-row");
    const list = row.parentElement;
    const action = button.dataset.action;
    if (action === "remove") {
      const next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      if (next) {
        const focusable = next.querySelector(`button[data-action="remove"]`);
        if (focusable) focusable.focus();
      }
    } else if (action === "up" && row.previousElementSibling) {
      list.insertBefore(row, row.previousElementSibling);
      button.focus();
    } else if (action === "down" && row.nextElementSibling) {
      list.insertBefore(row.nextElementSibling, row);
      button.focus();
    }
    renumberSteps(list);
  });
}

// ---------- Cook mode: one big step at a time, screen stays on ----------
// Steps slide like pages: Next slides the old step out to the left and the
// new one in from the right (Previous does the opposite). On a phone you
// can swipe. With "reduce motion" turned on, steps fade instead.

let wakeLock = null;

async function keepScreenOn(status) {
  if (!("wakeLock" in navigator)) {
    if (status) status.textContent = "Tip: this browser can't keep the screen on, so tap it now and then.";
    return;
  }
  try {
    wakeLock = await navigator.wakeLock.request("screen");
    if (status) status.textContent = "The screen will stay on while you cook.";
    wakeLock.addEventListener("release", () => {
      wakeLock = null;
    });
  } catch (e) {
    if (status) status.textContent = "Tip: the screen may turn off, so tap it now and then.";
  }
}

const SLIDE_OUT_MS = 180;
const SLIDE_IN_MS = 260;

function slideFrames(direction, entering) {
  // direction 1 = next (move left), -1 = previous (move right).
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const away = reduce ? "0" : `${-direction * 40}%`;
  const from = reduce ? "0" : `${direction * 40}%`;
  if (entering) {
    return [
      { transform: `translateX(${from})`, opacity: 0 },
      { transform: "translateX(0)", opacity: 1 },
    ];
  }
  return [
    { transform: "translateX(0)", opacity: 1 },
    { transform: `translateX(${away})`, opacity: 0 },
  ];
}

function setUpCookMode() {
  const cook = document.querySelector("[data-cook]");
  if (!cook) return;
  const steps = Array.from(cook.querySelectorAll(".cook-all li")).map((li) => li.textContent.trim());
  const text = cook.querySelector("#cook-step");
  const progress = cook.querySelector("#cook-progress");
  const bar = cook.querySelector("#cook-bar");
  const back = cook.querySelector("#cook-back");
  const next = cook.querySelector("#cook-next");
  const status = cook.querySelector("#cook-status");
  if (!steps.length || !text) return;
  let index = 0;
  let moving = false;

  function show() {
    text.textContent = steps[index];
    progress.textContent = `Step ${index + 1} of ${steps.length}`;
    if (bar) bar.style.width = `${((index + 1) / steps.length) * 100}%`;
    back.disabled = index === 0;
    next.textContent = index === steps.length - 1 ? "Finish" : "Next step ›";
  }

  function go(direction) {
    const target = index + direction;
    if (moving || target < 0 || target >= steps.length) return;
    if (!text.animate) {
      index = target;
      show();
      return;
    }
    moving = true;
    const out = text.animate(slideFrames(direction, false), { duration: SLIDE_OUT_MS, easing: "ease-in" });
    out.onfinish = () => {
      index = target;
      show();
      const into = text.animate(slideFrames(direction, true), { duration: SLIDE_IN_MS, easing: "ease-out" });
      into.onfinish = () => {
        moving = false;
      };
    };
  }

  back.addEventListener("click", () => go(-1));
  next.addEventListener("click", () => {
    if (index < steps.length - 1) {
      go(1);
    } else if (next.dataset.done) {
      window.location.href = next.dataset.done;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") go(1);
    if (event.key === "ArrowLeft") go(-1);
  });

  // Swipe left for the next step, right for the previous one.
  let startX = null;
  let startY = null;
  const viewport = cook.querySelector(".cook-viewport") || text;
  viewport.addEventListener("pointerdown", (event) => {
    startX = event.clientX;
    startY = event.clientY;
  });
  viewport.addEventListener("pointerup", (event) => {
    if (startX === null) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    startX = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) go(dx < 0 ? 1 : -1);
  });
  // The lock is dropped when the tab is hidden; ask again when it's back.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && wakeLock === null) keepScreenOn(status);
  });
  show();
  keepScreenOn(status);
}

// ---------- Shopping list: remember what's ticked (on this device only) ----------

function setUpShoppingTicks() {
  const list = document.querySelector("[data-shopping-key]");
  if (!list) return;
  const key = `sangkap:shopping:${list.dataset.shoppingKey}`;
  let ticked = [];
  try {
    ticked = JSON.parse(localStorage.getItem(key) || "[]");
  } catch (e) {
    ticked = [];
  }
  const boxes = list.querySelectorAll("input[type=checkbox][data-item]");
  boxes.forEach((box) => {
    box.checked = ticked.includes(box.dataset.item);
    box.addEventListener("change", () => {
      const now = Array.from(boxes).filter((b) => b.checked).map((b) => b.dataset.item);
      try {
        localStorage.setItem(key, JSON.stringify(now));
      } catch (e) {
        // Storage can be blocked; the ticks then last until the page reloads.
      }
    });
  });
}

// ---------- Print buttons ----------

function setUpPrintButtons() {
  document.querySelectorAll("[data-print]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", () => window.print());
  });
}

document.addEventListener("DOMContentLoaded", () => {
  setUpThemeToggle();
  setUpMenu();
  setUpInstall();
  setUpConfirms();
  setUpAutosubmit();
  setUpPicker();
  setUpMealMenus();
  setUpRowEditing();
  setUpCookMode();
  setUpShoppingTicks();
  setUpPrintButtons();
});
