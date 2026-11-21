// Run: node --experimental-transform-types scripts/nav-access.check.ts
import assert from "node:assert/strict";
import { filterNavGroups } from "../src/lib/nav-access.ts";
import { can } from "../src/lib/utils.ts";
const filter = (g, perms) => filterNavGroups(g, (needed) => can(perms, needed));

const icon = (() => null) as never;
const groups = [
  { id: "main", label: "Main", items: [
    { id: "overview", label: "Overview", href: "/dashboard", icon },
    { id: "comm", label: "Comm", href: "/communication", icon, children: [
      { id: "calls", label: "Calls", href: "/c/calls", icon },
      { id: "voice", label: "Voice", href: "/c/voice", icon, permission: "voice:use" },
    ] },
    { id: "only-voice", label: "OnlyVoice", href: "/v", icon, children: [{ id: "v", label: "V", href: "/v/1", icon, permission: "voice:use" }] },
    { id: "cases", label: "Cases", href: "/cases", icon, permission: "cases:read" },
  ] },
  { id: "ops", label: "Ops", items: [{ id: "k", label: "K", href: "/k", icon, permission: "knowledge:read" }] },
];
const ids = (g) => g.flatMap((x) => x.items.flatMap((i) => [i.id, ...(i.children ?? []).map((c) => c.id)]));

assert.deepEqual(ids(filter(groups, ["*"])), ["overview", "comm", "calls", "voice", "only-voice", "v", "cases", "k"]);
assert.deepEqual(ids(filter(groups, ["cases:write"])), ["overview", "comm", "calls", "cases"]); // write implies read; "only-voice" and the Ops group vanish when empty
assert.deepEqual(ids(filter(groups, [])), ["overview", "comm", "calls"]);
assert.deepEqual(ids(filter(groups, undefined)), ["overview", "comm", "calls"]); // not signed in yet: only the unrestricted items
assert.equal(filter(groups, ["knowledge:read"]).length, 2);
assert.equal(groups[0].items.length, 4); // the input is not mutated
console.log("nav-access checks passed");
