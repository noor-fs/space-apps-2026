// The five targets and their field centers (RA/Dec on 2026-01-01), from the plan.
export const TARGETS = [
  { key: "epsilon_indi_b", name: "Epsilon Indi B", ra: 331.096653, dec: -56.800663,
    aliases: ["eps indi b", "ε indi b", "epsilon indi"] },
  { key: "barnards_star", name: "Barnard's Star", ra: 269.446268, dec: 4.768204,
    aliases: ["barnard", "gj 699", "v2500 oph"] },
  { key: "r_draconis", name: "R Draconis", ra: 248.167233, dec: 66.755024,
    aliases: ["r dra"] },
  { key: "rw_aurigae", name: "RW Aurigae", ra: 76.956560, dec: 30.401248,
    aliases: ["rw aur"] },
  // WISE 0855 center from Yara T's team update (2026-11-14), replacing the plan's provisional 133.79, -7.245.
  { key: "wise_0855", name: "WISE 0855", ra: 133.760346, dec: -7.241822,
    aliases: ["wise 0855-0714", "wise j0855-0714", "wise j085510.83-071442.5"] },
];

// Fake targets made only for testing the site. Reachable by button, name or ?target=.
// They are left out of coordinate search so they never hide a real target.
export const TEST_TARGETS = [
  // Fake-only targets start with "fake_" (team rule in PROJECT_STRUCTURE.md).
  { key: "fake_saturated", name: "Fake: saturated star", ra: 269.446268, dec: 4.768204,
    aliases: ["saturated", "test saturated"] },
];

export const ALL_TARGETS = [...TARGETS, ...TEST_TARGETS];

export function targetByKey(key) {
  return ALL_TARGETS.find((t) => t.key === key) || null;
}

const norm = (s) => s.toLowerCase().normalize("NFKD").replace(/[^a-z0-9ε]/g, "");

/** Match a typed name against target names, keys and aliases. */
export function findTargetByName(query) {
  const q = norm(query);
  if (!q) return null;
  const names = (t) => [t.name, t.key, ...(t.aliases || [])].map(norm);
  const exact = ALL_TARGETS.find((t) => names(t).includes(q));
  if (exact) return exact;
  if (q.length < 3) return null;
  return ALL_TARGETS.find((t) => names(t).some((n) => n.startsWith(q) || n.includes(q))) || null;
}
