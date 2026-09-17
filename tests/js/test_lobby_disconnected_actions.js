"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.className = "";
    this.dataset = {};
    this.style = {};
    this.textContent = "";
    this.innerHTML = "";
    this.value = "";
    this.checked = false;
    this.disabled = false;
    this.classList = {
      add: (...names) => {
        const classes = new Set(this.className.split(/\s+/).filter(Boolean));
        names.forEach((name) => classes.add(name));
        this.className = [...classes].join(" ");
      },
      remove: (...names) => {
        const removed = new Set(names);
        this.className = this.className
          .split(/\s+/)
          .filter((name) => name && !removed.has(name))
          .join(" ");
      },
    };
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  prepend(child) {
    this.children.unshift(child);
  }

  addEventListener() {}

  dispatchEvent() {}

  closest() {
    return null;
  }
}

const elements = new Map();
const getElement = (id) => {
  if (!elements.has(id)) elements.set(id, new FakeElement());
  return elements.get(id);
};
const handlers = {};
const socket = {
  connect() {},
  emit() {},
  on(eventName, handler) {
    handlers[eventName] = handler;
  },
};
const context = {
  Array,
  DOMPurify: { sanitize: (value) => value },
  Event: class {},
  Math,
  Object,
  Set,
  alert() {},
  confirm: () => true,
  console,
  currentPlayerId: "admin",
  document: {
    createElement: (tagName) => new FakeElement(tagName),
    documentElement: {},
    getElementById: getElement,
    querySelector: () => new FakeElement(),
    querySelectorAll: () => [],
    title: "",
  },
  fetch: async () => ({ ok: true, json: async () => ({}) }),
  io: () => socket,
  isNaN,
  parseFloat,
  window: { location: {}, userLang: "en" },
};

const lobbyPath = path.resolve(__dirname, "../../static/lobby.js");
vm.runInNewContext(fs.readFileSync(lobbyPath, "utf8"), context, {
  filename: lobbyPath,
});

handlers.update_player_list({
  admin_only_chat: false,
  game_code: "W",
  players: [
    {
      connection_state: "connected",
      id: "admin",
      is_admin: true,
      name: "Admin",
    },
    {
      connection_state: "disconnected",
      id: "target",
      is_admin: false,
      name: "Target",
    },
  ],
});

const targetRow = getElement("player-list").children[1];
const actionLabels = targetRow.children.map((child) => child.textContent);
assert(actionLabels.includes("ui.lobby.exclude_btn"));
assert(!actionLabels.includes("🪄"));
