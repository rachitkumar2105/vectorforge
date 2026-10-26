import assert from "node:assert/strict";
import { test } from "node:test";

import { buildGraph, exactKnn, makeDataset, searchTrace } from "../lib/hnsw.ts";

const points = makeDataset(300, 7);
const graph = buildGraph(points, { M: 6, efConstruction: 32, seed: 1 });

test("dataset is deterministic and inside the unit square", () => {
  assert.deepEqual(makeDataset(50, 3), makeDataset(50, 3));
  for (const p of points) {
    assert.ok(p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1);
  }
});

test("graph invariants: symmetric links, degree caps, every node on layer 0", () => {
  for (let node = 0; node < points.length; node++) {
    const layers = graph.links[node]!;
    assert.equal(layers.length, graph.levels[node]! + 1);
    layers.forEach((nbrs, layer) => {
      const cap = layer === 0 ? 2 * graph.M : graph.M;
      assert.ok(nbrs.length <= cap, `degree ${nbrs.length} > ${cap}`);
      assert.ok(!nbrs.includes(node), "self loop");
      for (const other of nbrs) {
        assert.ok(graph.links[other]![layer]!.includes(node), `one-way edge ${node}->${other}`);
      }
    });
  }
  assert.equal(graph.levels[graph.entry], graph.maxLevel);
  assert.equal(Math.max(...graph.levels), graph.maxLevel);
});

test("build is deterministic under a fixed seed", () => {
  const again = buildGraph(points, { M: 6, efConstruction: 32, seed: 1 });
  assert.deepEqual(again.links, graph.links);
  assert.equal(again.entry, graph.entry);
});

test("search recall@5 is high and the trace descends layer by layer", () => {
  const queries = makeDataset(40, 99);
  let hits = 0;
  for (const q of queries) {
    const { results, events } = searchTrace(graph, q, 5, 24);
    const truth = exactKnn(points, q, 5);
    hits += results.filter((r) => truth.includes(r)).length;
    const layers = events.filter((e) => e.kind === "enter").map((e) => e.layer);
    assert.deepEqual(layers, [...layers].sort((a, b) => b - a), "layers must descend");
    assert.equal(layers.at(-1), 0);
    assert.equal(events.at(-1)!.kind, "result");
  }
  assert.ok(hits / (queries.length * 5) > 0.9, `recall ${hits / (queries.length * 5)}`);
});

test("larger ef visits at least as many nodes on layer 0", () => {
  const q = { x: 0.42, y: 0.58 };
  const visits = [4, 16, 64].map(
    (ef) => searchTrace(graph, q, 4, ef).events.filter((e) => e.kind === "visit" && e.layer === 0).length,
  );
  assert.ok(visits[0]! <= visits[1]! && visits[1]! <= visits[2]!, String(visits));
});

test("frontier snapshots are reported for every expansion", () => {
  const { events } = searchTrace(graph, { x: 0.1, y: 0.9 }, 3, 12);
  const expands = events.filter((e) => e.kind === "expand");
  assert.ok(expands.length > 0);
  for (const e of expands) {
    if (e.kind === "expand") assert.ok(Array.isArray(e.frontier));
  }
});

test("tiny graphs work", () => {
  const one = buildGraph([{ x: 0.5, y: 0.5 }], { M: 4, efConstruction: 8, seed: 0 });
  assert.deepEqual(searchTrace(one, { x: 0, y: 0 }, 3, 8).results, [0]);
  const empty = buildGraph([], { M: 4, efConstruction: 8, seed: 0 });
  assert.deepEqual(searchTrace(empty, { x: 0, y: 0 }, 3, 8).results, []);
});
