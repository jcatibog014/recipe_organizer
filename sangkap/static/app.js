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

// ---------- "Are you sure?" before deleting ----------
// A form with data-confirm="Question?" asks first. Without JavaScript it just sends.

function setUpConfirms() {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
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

let wakeLock = null;

async function keepScreenOn(status) {
  if (!("wakeLock" in navigator)) {
    if (status) status.textContent = "Tip: this browser can't keep the screen on by itself.";
    return;
  }
  try {
    wakeLock = await navigator.wakeLock.request("screen");
    if (status) status.textContent = "☀️ The screen will stay on while you cook.";
    wakeLock.addEventListener("release", () => {
      wakeLock = null;
    });
  } catch (e) {
    if (status) status.textContent = "Tip: the screen may turn off. Tap it now and then.";
  }
}

function setUpCookMode() {
  const cook = document.querySelector("[data-cook]");
  if (!cook) return;
  const steps = Array.from(cook.querySelectorAll(".cook-all li")).map((li) => li.textContent.trim());
  const text = cook.querySelector("#cook-step");
  const progress = cook.querySelector("#cook-progress");
  const back = cook.querySelector("#cook-back");
  const next = cook.querySelector("#cook-next");
  const status = cook.querySelector("#cook-status");
  if (!steps.length || !text) return;
  let index = 0;

  function show() {
    text.textContent = steps[index];
    progress.textContent = `Step ${index + 1} of ${steps.length}`;
    back.disabled = index === 0;
    next.textContent = index === steps.length - 1 ? "All done! 🎉" : "Next step ›";
  }

  back.addEventListener("click", () => {
    if (index > 0) index -= 1;
    show();
  });
  next.addEventListener("click", () => {
    if (index < steps.length - 1) {
      index += 1;
      show();
    } else if (next.dataset.done) {
      window.location.href = next.dataset.done;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") next.click();
    if (event.key === "ArrowLeft") back.click();
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
  setUpConfirms();
  setUpRowEditing();
  setUpCookMode();
  setUpShoppingTicks();
  setUpPrintButtons();
});
